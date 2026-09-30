"""Paired live timings on synthetic cases; never changes production settings.

Run explicitly, outside CI quality gates. Outputs contain only synthetic data.
The worksheet phase runs only when the candidate is faster on reporting.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path.cwd()))

from evals.clinical_quality import evaluate_case, load_cases


def summarise(rows):
    groups = {}
    for row in rows:
        key = f"{row['task']}:{row['model']}"
        groups.setdefault(key, []).append(row)
    return {
        key: {
            "n": len(group),
            "completed": sum(not r.get("error") for r in group),
            "median_seconds": statistics.median(r["seconds"] for r in group),
            "max_seconds": max(r["seconds"] for r in group),
            "median_first_text_seconds": statistics.median(
                r["first_text_seconds"] for r in group if r.get("first_text_seconds") is not None
            ) if any(r.get("first_text_seconds") is not None for r in group) else None,
            "gate_passes": sum(r.get("checks", {}).get("passed", False) for r in group),
        }
        for key, group in groups.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("Use 1 to 5 repeats")
    logging.disable(logging.CRITICAL)
    from config.config import config
    from config.settings import load_settings
    from config import practice
    from llm import model_compat, format as report_format, impressions, worksheet
    from llm.text_client import get_text_client

    load_settings(web_mode=True)
    if not config.TEXT_API_KEY or practice.settings.text_provider != "openai":
        raise RuntimeError("Benchmark requires the existing OpenAI text provider")
    if config.BASE_URL.rstrip("/") != "https://api.openai.com/v1":
        raise RuntimeError("Benchmark requires the direct OpenAI endpoint")
    baseline = config.SELECTED_MODEL
    if baseline != "gpt-6-sol":
        raise RuntimeError("Production baseline has changed; review before benchmarking")
    candidate = "gpt-6.1-sol"
    models = [baseline, candidate]
    original_effort = model_compat.reasoning_effort_for_model
    # Process-local compatibility only. Keep live workers and saved settings intact.
    model_compat.reasoning_effort_for_model = lambda model: (
        "low" if model in models else original_effort(model)
    )
    client = get_text_client().with_options(timeout=90, max_retries=0)
    original_create = client.chat.completions.create
    def create(**kwargs):
        # Both models use the same paid processing tier and reasoning budget.
        kwargs["service_tier"] = "default"
        kwargs["reasoning_effort"] = "low"
        return original_create(**kwargs)
    client.chat.completions.create = create
    for module in (report_format, impressions, worksheet):
        module.get_text_client = lambda *unused: client

    rows = []
    payload = {
        "baseline": baseline, "candidate": candidate,
        "reasoning_effort": "low", "service_tier": "default",
        "repeats": args.repeats,
        "method": "Serial paired AB/BA calls; same prompts, templates, processing tier and server",
        "scope": "Synthetic cases only; timings exclude audio transcription, browser and clipboard",
        "production_settings_changed": False,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        payload["summary"] = summarise(rows)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def measure(task, case_id, model, repeat, function, check=None):
        config.SELECTED_MODEL = model
        row = {"task": task, "case_id": case_id, "model": model, "repeat": repeat}
        start = time.perf_counter()
        first = None
        try:
            result = function()
            if isinstance(result, str):
                report = result
            elif isinstance(result, worksheet.WorksheetDraft):
                report = result.report
                row["source_notes"] = result.source_notes
            else:
                parts = []
                for part in result:
                    if part and first is None:
                        first = time.perf_counter() - start
                    parts.append(part)
                report = report_format.postprocess_report("".join(parts))
            row["report"] = report
            if check:
                evaluated_report = "IMPRESSION:\n" + report if task == "impression" else report
                row["checks"] = asdict(evaluate_case(check, evaluated_report))
                row["checks"].pop("report", None)
        except Exception as exc:
            # Never serialize provider exceptions: they can include request content.
            row["error"] = {"type": type(exc).__name__, "status": getattr(exc, "status_code", None)}
        row["seconds"] = time.perf_counter() - start
        row["first_text_seconds"] = first
        rows.append(row)
        save()
        print(json.dumps({k: row.get(k) for k in ("task", "case_id", "model", "repeat", "seconds", "error")}), flush=True)
        return not row.get("error")

    cases = load_cases()
    # Fail quickly on unavailable candidate, rather than spending on an invalid comparison.
    for model in models:
        if not measure("availability", "probe", model, 0,
                       lambda: client.chat.completions.create(
                           model=model, messages=[{"role": "user", "content": "Reply with OK."}],
                           max_completion_tokens=2048,
                       ).choices[0].message.content or ""):
            payload["worksheet_phase"] = "skipped: model unavailable"
            save()
            return 1
    for repeat in range(args.repeats):
        for index, case in enumerate(cases):
            order = models if (repeat + index) % 2 == 0 else models[::-1]
            template = report_format._get_template_content(case["template"])
            for model in order:
                measure("report", case["id"], model, repeat,
                        lambda: report_format.stream_format_text(case["transcript"], template_content=template), case)
            if case["id"] in {"ctpa_right_lower_lobe_embolus", "mri_knee_medial_meniscus", "mri_brain_left_infarct"}:
                check = dict(case, section_order=[], measurements=[], laterality=case["laterality"][:1])
                if case["id"] == "mri_knee_medial_meniscus":
                    check["required_any"] = case["required_any"][:2]
                # Impression-only outputs do not contain section headings.
                for model in order:
                    measure("impression", case["id"], model, repeat,
                            lambda: impressions.stream_impression(case["transcript"], modality=case["template"], with_guidelines=True),
                            dict(check, section_order=["impression"]))

    summary = summarise(rows)
    faster = any(
        summary[f"{task}:{candidate}"]["completed"] == summary[f"{task}:{candidate}"]["n"]
        and summary[f"{task}:{baseline}"]["completed"] == summary[f"{task}:{baseline}"]["n"]
        and summary[f"{task}:{candidate}"]["median_seconds"] <= 0.9 * summary[f"{task}:{baseline}"]["median_seconds"]
        for task in ("report", "impression")
    )
    payload["candidate_faster_by_at_least_10_percent"] = faster
    if not faster:
        payload["worksheet_phase"] = "skipped: candidate did not meet reporting speed threshold"
        save()
        return 0

    payload["worksheet_phase"] = "running"
    template = report_format._get_template_content("Ultrasound_Worksheet.txt")
    for repeat in range(args.repeats):
        for index, name in enumerate(("renal", "obstetric")):
            images = worksheet.validate_worksheet_images([
                (Path("web/static/reports/worksheet-speed-2026-09-24") / f"{name}.png").read_bytes()
            ])
            order = models if (repeat + index) % 2 == 0 else models[::-1]
            for route in ("worksheet_one_step", "worksheet_two_step"):
                for model in order:
                    def generate():
                        if route == "worksheet_one_step":
                            return worksheet.draft_worksheet_report(images, template_content=template, reasoning_effort="low")
                        notes = worksheet.extract_worksheet_findings(images)
                        report = report_format.postprocess_report("".join(report_format.stream_format_text(
                            notes, template_content=template, source_kind="worksheet"
                        )))
                        return worksheet.WorksheetDraft(source_notes=notes, report=report)
                    measure(route, name, model, repeat, generate)
    payload["worksheet_phase"] = "complete"
    config.SELECTED_MODEL = baseline
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
