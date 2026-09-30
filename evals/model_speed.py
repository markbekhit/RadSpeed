"""Paired live timings on synthetic cases; never changes production settings.

Run explicitly, outside CI quality gates. Outputs contain only synthetic data.
Worksheet comparisons run by default. Add --reports to repeat text comparisons.
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
    parser.add_argument("--reports", action="store_true", help="Also repeat report and impression comparisons")
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
    api_calls = []
    def create(**kwargs):
        # Both models use the same paid processing tier and reasoning budget.
        kwargs["service_tier"] = "default"
        kwargs["reasoning_effort"] = "low"
        started = time.perf_counter()
        record = {"model": kwargs["model"], "stream": bool(kwargs.get("stream"))}
        api_calls.append(record)
        if kwargs.get("stream"):
            kwargs["stream_options"] = {"include_usage": True}
        response = original_create(**kwargs)
        def capture(value):
            usage = getattr(value, "usage", None)
            if usage:
                record["usage"] = usage.model_dump()
            tier = getattr(value, "service_tier", None)
            if tier:
                record["service_tier"] = tier
            record["seconds"] = time.perf_counter() - started
        if not kwargs.get("stream"):
            capture(response)
            return response
        def chunks():
            for chunk in response:
                capture(chunk)
                yield chunk
        return chunks()
    client.chat.completions.create = create
    for module in (report_format, impressions, worksheet):
        module.get_text_client = lambda *unused: client

    rows = []
    payload = {
        "baseline": baseline, "candidate": candidate,
        "reasoning_effort": "low", "service_tier": "default",
        "repeats": args.repeats, "include_reports": args.reports,
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
        call_start = len(api_calls)
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
        row["api_calls"] = api_calls[call_start:]
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
    if args.reports:
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
