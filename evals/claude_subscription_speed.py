"""Synthetic RadSpeed benchmarks through the authenticated Claude Code subscription.

Uses the existing application prompts. Never reads credentials or calls a paid API.
CLI and provider timings are distinct; historical OpenAI API timings are not paired.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.clinical_quality import evaluate_case, load_cases
from evals.model_speed import summarise
from llm.text_client import convert_messages

MODEL = "claude-sonnet-5-5"


class SubscriptionClient:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=self)
        self.env = os.environ.copy()
        for name in (
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
        ):
            self.env.pop(name, None)

    def create(self, *, model, messages, stream=False, **options):
        if model != MODEL or options.get("tools"):
            raise ValueError("Only the requested Sonnet model and tool-free prompts are supported")
        system, converted = convert_messages(messages)
        if len(converted) != 1 or converted[0]["role"] != "user":
            raise ValueError("Benchmark requires one synthetic user message")
        record = {"requested_model": model, "stream": stream, "effort": "low"}
        self.calls.append(record)
        def generate():
            started = time.perf_counter()
            texts = []
            with tempfile.TemporaryDirectory(prefix="radspeed-sonnet-") as directory:
                prompt = Path(directory) / "prompt.jsonl"
                prompt.write_text(json.dumps({"type": "user", "message": converted[0]}) + "\n")
                command = [
                    shutil.which("claude"), "-p", "--safe-mode", "--disable-slash-commands",
                    "--tools", "", "--model", MODEL, "--effort", "low",
                    "--input-format", "stream-json", "--output-format", "stream-json",
                    "--verbose", "--include-partial-messages", "--no-session-persistence",
                    "--system-prompt", system,
                ]
                with prompt.open() as incoming, (Path(directory) / "stderr.txt").open("w") as errors:
                    process = subprocess.Popen(command, stdin=incoming, stdout=subprocess.PIPE,
                                               stderr=errors, text=True, cwd=directory, env=self.env)
                    deadline = threading.Timer(120, lambda: process.kill() if process.poll() is None else None)
                    deadline.start()
                    try:
                        for line in process.stdout:
                            event = json.loads(line)
                            if event.get("type") == "stream_event":
                                delta = event.get("event", {}).get("delta", {})
                                if delta.get("type") == "text_delta" and delta.get("text"):
                                    text = delta["text"]
                                    texts.append(text)
                                    record.setdefault("first_text_seconds", time.perf_counter() - started)
                                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])
                            elif event.get("type") == "assistant":
                                record["returned_model"] = event.get("message", {}).get("model")
                            elif event.get("type") == "result":
                                if event.get("is_error"):
                                    raise RuntimeError("Claude Code returned an unsuccessful result")
                                record["provider_seconds"] = event.get("duration_api_ms", 0) / 1000
                                record["cli_reported_seconds"] = event.get("duration_ms", 0) / 1000
                                record["usage"] = event.get("usage", {})
                                record["model_usage"] = {
                                    k: {n: v.get(n) for n in ("provider", "canonicalModel", "inputTokens", "outputTokens", "thinkingTokens", "cacheReadInputTokens", "cacheCreationInputTokens")}
                                    for k, v in event.get("modelUsage", {}).items()
                                }
                                if not texts and event.get("result"):
                                    texts.append(event["result"])
                                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=event["result"]))])
                        if process.wait(timeout=10) != 0:
                            raise RuntimeError("Claude Code exited unsuccessfully")
                        if record.get("returned_model") != MODEL:
                            raise RuntimeError("Claude Code did not confirm the requested model")
                        if any(v.get("provider") != "firstParty" for v in record.get("model_usage", {}).values()):
                            raise RuntimeError("Unexpected Claude provider")
                        record["seconds"] = time.perf_counter() - started
                        record["raw_text"] = "".join(texts)
                    finally:
                        deadline.cancel()
                        if process.poll() is None:
                            process.kill()
                            process.wait()
        chunks = generate()
        if stream:
            return chunks
        text = "".join(chunk.choices[0].delta.content for chunk in chunks)
        if options.get("response_format", {}).get("type") == "json_object":
            # Claude Code does not expose OpenAI's response_format contract.
            # Remove an outer Markdown fence only; do not repair JSON or facts.
            cleaned = text.strip()
            if cleaned.startswith("```") and cleaned.endswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                record["outer_json_fence_removed"] = True
            text = cleaned
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def main():
    logging.disable(logging.CRITICAL)
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    output = root / "reports/sonnet-subscription-comparison-2026-09-30/results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    auth = json.loads(subprocess.check_output(["claude", "auth", "status"], text=True))
    if not auth.get("loggedIn") or auth.get("authMethod") != "claude.ai" or auth.get("subscriptionType") != "max":
        raise RuntimeError("The existing Claude Max subscription session is required")
    from config.config import config
    from llm import format as report_format, impressions, worksheet
    config.SELECTED_MODEL = MODEL
    client = SubscriptionClient()
    for module in (report_format, impressions, worksheet):
        module.get_text_client = lambda *unused: client
    previous = json.loads(output.read_text()) if output.exists() else {}
    failed_attempts = previous.get("failed_attempts", []) + [r for r in previous.get("rows", []) if r.get("error")]
    rows = [r for r in previous.get("rows", []) if not r.get("error")]
    completed = {(r["task"], r["case_id"], r["repeat"]) for r in rows}
    payload = {
        "model": MODEL, "auth_method": "claude.ai", "subscription": "max",
        "provider": "Claude Code firstParty", "effort": "low", "repeats": 3,
        "production_settings_changed": False, "baseline_models_retested": False,
        "method": "Serial Claude Code subscription calls using existing RadSpeed functions and synthetic inputs. CLI overhead included in wall time. Provider-reported time also captured. Comparison baselines are historical API runs.",
        "rows": rows, "failed_attempts": failed_attempts,
        "json_adapter": "Remove outer Markdown JSON fences to supply the requested JSON-object response contract. Never change JSON contents.",
    }
    def save():
        payload["summary"] = summarise(rows)
        output.write_text(json.dumps(payload, indent=2))
    def measure(task, case_id, repeat, function, check=None):
        if (task, case_id, repeat) in completed:
            return
        started = time.perf_counter()
        call_start = len(client.calls)
        first = None
        row = {"model": MODEL, "task": task, "case_id": case_id, "repeat": repeat}
        try:
            result = function()
            if isinstance(result, worksheet.WorksheetDraft):
                report = result.report
                row["source_notes"] = result.source_notes
            else:
                parts = []
                for part in result:
                    if part and first is None:
                        first = time.perf_counter() - started
                    parts.append(part)
                report = report_format.postprocess_report("".join(parts))
            row["report"] = report
            if check:
                row["checks"] = asdict(evaluate_case(check, "IMPRESSION:\n" + report if task == "impression" else report))
                row["checks"].pop("report", None)
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__}
        row["seconds"] = time.perf_counter() - started
        row["first_text_seconds"] = first
        row["api_calls"] = client.calls[call_start:]
        row["provider_seconds"] = sum(c.get("provider_seconds", 0) for c in row["api_calls"])
        rows.append(row)
        save()
        print(json.dumps({k: row.get(k) for k in ("task", "case_id", "repeat", "seconds", "provider_seconds", "error")}), flush=True)
    cases = load_cases()
    for repeat in range(3):
        for case in cases:
            template = report_format._get_template_content(case["template"])
            measure("report", case["id"], repeat,
                    lambda: report_format.stream_format_text(case["transcript"], template_content=template), case)
            if case["id"] in {"ctpa_right_lower_lobe_embolus", "mri_knee_medial_meniscus", "mri_brain_left_infarct"}:
                check = dict(case, section_order=["impression"], measurements=[], laterality=case["laterality"][:1])
                if case["id"] == "mri_knee_medial_meniscus":
                    check["required_any"] = case["required_any"][:2]
                measure("impression", case["id"], repeat,
                        lambda: impressions.stream_impression(case["transcript"], modality=case["template"], with_guidelines=True), check)
        template = report_format._get_template_content("Ultrasound_Worksheet.txt")
        for name in ("renal", "obstetric"):
            images = worksheet.validate_worksheet_images([(root / "web/static/reports/worksheet-speed-2026-09-24" / f"{name}.png").read_bytes()])
            measure("worksheet_one_step", name, repeat,
                    lambda: worksheet.draft_worksheet_report(images, template_content=template, reasoning_effort="low"))
            def two_step():
                notes = worksheet.extract_worksheet_findings(images)
                report = report_format.postprocess_report("".join(report_format.stream_format_text(notes, template_content=template, source_kind="worksheet")))
                return worksheet.WorksheetDraft(source_notes=notes, report=report)
            measure("worksheet_two_step", name, repeat, two_step)
    payload["complete"] = True
    save()
    return int(any(r.get("error") for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
