"""Subscription-only Sonnet 5.5 reassessment on synthetic RadSpeed cases.

Uses the authenticated first-party Claude Code CLI (Max subscription) and the real
RadSpeed prompt/template functions. It never reads credentials, never calls a paid
API and never calls Sol: saved Sol results are read for comparison only.
Each underlying model call is a fresh CLI process, because a persistent process
would carry conversation history and is not equivalent to a stateless API request.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import re
import shutil
import statistics
import queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.clinical_quality import evaluate_case, load_cases
from llm.text_client import convert_messages

MODEL = "claude-sonnet-5-5"
OUT = ROOT / "reports/sonnet-reassessment-2026-10-01"
CONDITIONS = {
    # Same technique as the 30 September run (new process per call, default CLI environment).
    "cli_default": {},
    # Same prompts and flags. Only documented environment switch: no telemetry/updater traffic.
    "cli_lean": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
    # Exploratory: requests no thinking after the first two conditions.
    # Returned usage still reported thinking on some calls; this is not a verified zero-thinking condition.
    "cli_lean_no_thinking": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "MAX_THINKING_TOKENS": "0"},
}
SECRET_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_CODE_OAUTH", "OPENROUTER_", "AWS_BEARER_TOKEN_BEDROCK")
SECRET_PATTERN = re.compile(r"^CLAUDE.*(KEY|TOKEN|HELPER)", re.I)
IMPRESSION_CASES = {"ctpa_right_lower_lobe_embolus", "mri_knee_medial_meniscus", "mri_brain_left_infarct"}
CALL_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def child_environment(extra=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(SECRET_PREFIXES) and not SECRET_PATTERN.match(k)}
    removed = len(os.environ) - len(env)
    env.update(extra or {})
    return env, removed


def base_command(system):
    return [
        shutil.which("claude"), "-p", "--safe-mode", "--disable-slash-commands",
        "--tools", "", "--model", MODEL, "--effort", "low",
        "--input-format", "stream-json", "--output-format", "stream-json",
        "--verbose", "--include-partial-messages", "--no-session-persistence",
        "--system-prompt", system,
    ]


def auth_summary():
    data = json.loads(subprocess.check_output(["claude", "auth", "status"], text=True))
    return {k: data.get(k) for k in ("loggedIn", "authMethod", "subscriptionType", "apiProvider")}


def run_process(system, message, env, directory, stream_callback=None):
    """One fresh Claude Code process. Returns (text, record)."""
    record = {"requested_model": MODEL, "effort": "low"}
    prompt = Path(directory) / "prompt.jsonl"
    prompt.write_text(json.dumps({"type": "user", "message": message}) + "\n")
    texts = []
    started = time.perf_counter()
    with prompt.open() as incoming, (Path(directory) / "stderr.txt").open("w") as errors:
        process = subprocess.Popen(base_command(system), stdin=incoming, stdout=subprocess.PIPE,
                                   stderr=errors, text=True, cwd=directory, env=env)
        deadline = threading.Timer(120, lambda: process.kill() if process.poll() is None else None)
        deadline.start()
        try:
            for line in process.stdout:
                now = time.perf_counter() - started
                event = json.loads(line)
                kind = event.get("type")
                if kind == "system" and event.get("subtype") == "init":
                    record.setdefault("init_seconds", now)
                    record["api_key_source"] = event.get("apiKeySource")
                    record["tools_available"] = event.get("tools")
                    record["slash_commands_available"] = event.get("slash_commands")
                elif kind == "stream_event":
                    inner = event.get("event", {})
                    if inner.get("type") == "message_start":
                        record.setdefault("message_start_seconds", now)
                    delta = inner.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        record.setdefault("first_text_seconds", now)
                        texts.append(delta["text"])
                        if stream_callback:
                            stream_callback(delta["text"])
                elif kind == "assistant":
                    record["returned_model"] = event.get("message", {}).get("model")
                elif kind == "result":
                    record["result_seconds"] = now
                    if event.get("is_error"):
                        raise RuntimeError("Claude Code returned an unsuccessful result")
                    record["provider_seconds"] = event.get("duration_api_ms", 0) / 1000
                    record["cli_reported_seconds"] = event.get("duration_ms", 0) / 1000
                    usage = event.get("usage", {})
                    record["usage"] = {k: usage.get(k) for k in CALL_FIELDS}
                    record["usage"]["thinking_tokens"] = usage.get("output_tokens_details", {}).get("thinking_tokens")
                    record["model_usage"] = {
                        k: {n: v.get(n) for n in ("provider", "canonicalModel")}
                        for k, v in event.get("modelUsage", {}).items()
                    }
                    if not texts and event.get("result"):
                        texts.append(event["result"])
                        if stream_callback:
                            stream_callback(event["result"])
            if process.wait(timeout=15) != 0:
                raise RuntimeError("Claude Code exited unsuccessfully")
            record["exit_seconds"] = time.perf_counter() - started
        finally:
            deadline.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
    if record.get("returned_model") != MODEL:
        raise RuntimeError("Claude Code did not confirm the requested model")
    if record.get("api_key_source") != "none":
        raise RuntimeError("Session is not using subscription authentication")
    if record.get("tools_available") or record.get("slash_commands_available"):
        raise RuntimeError("Tools or slash commands were not disabled")
    if not record.get("model_usage") or any(v.get("provider") != "firstParty" for v in record["model_usage"].values()):
        raise RuntimeError("Unexpected Claude provider")
    record["raw_text"] = "".join(texts)
    return record["raw_text"], record


class SubscriptionClient:
    """Minimal OpenAI-shaped client so the existing RadSpeed functions run unchanged."""

    def __init__(self, name, extra_env):
        self.name = name
        self.calls = []
        self.chat = SimpleNamespace(completions=self)
        self.env, self.removed_env_count = child_environment(extra_env)

    def create(self, *, model, messages, stream=False, **options):
        if model != MODEL or options.get("tools"):
            raise ValueError("Only the requested Sonnet model and tool-free prompts are supported")
        system, converted = convert_messages(messages)
        if len(converted) != 1 or converted[0]["role"] != "user":
            raise ValueError("Benchmark requires one synthetic user message")
        record = {"stream": stream, "condition": self.name}
        self.calls.append(record)

        def generate():
            inbox = queue.Queue()

            def work():
                try:
                    with tempfile.TemporaryDirectory(prefix="radspeed-sonnet-") as directory:
                        _, detail = run_process(system, converted[0], self.env, directory, inbox.put)
                    inbox.put(detail)
                except Exception as exc:
                    inbox.put(exc)

            threading.Thread(target=work, daemon=True).start()
            while True:
                item = inbox.get()
                if isinstance(item, str):
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=item))])
                    continue
                if isinstance(item, Exception):
                    raise item
                record.update(item)
                return

        if stream:
            return generate()
        text = "".join(chunk.choices[0].delta.content for chunk in generate())
        if options.get("response_format", {}).get("type") == "json_object":
            # Claude Code has no response_format contract: remove an outer fence only.
            cleaned = text.strip()
            if cleaned.startswith("```") and cleaned.endswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                record["outer_json_fence_removed"] = True
            text = cleaned
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def summarise(rows):
    groups = {}
    for row in rows:
        groups.setdefault(f"{row['condition']}:{row['task']}", []).append(row)
    out = {}
    for key, group in groups.items():
        ok = [r for r in group if not r.get("error")]
        out[key] = {
            "n": len(group), "completed": len(ok),
            "median_total_seconds": median(r["seconds"] for r in ok),
            "median_release_seconds": median(r["release_seconds"] for r in ok),
            "median_request_window_seconds": median(r["request_window_seconds"] for r in ok),
            "median_provider_seconds": median(r["provider_seconds"] for r in ok),
            "median_startup_seconds": median(r["startup_seconds"] for r in ok),
            "median_teardown_seconds": median(r["teardown_seconds"] for r in ok),
            "median_first_text_seconds": median(r["first_text_seconds"] for r in ok),
            "median_output_tokens": median(sum(c["usage"]["output_tokens"] for c in r["calls"]) for r in ok),
            "fenced_json_responses": sum(bool(c.get("outer_json_fence_removed")) for r in ok for c in r["calls"]),
            "phrase_gate_passes": sum(r.get("checks", {}).get("passed", False) for r in ok),
        }
    return out


def floor_probe(repeats):
    """Trivial synthetic prompt: isolates process overhead from task-dependent generation."""
    rows = []
    names = list(CONDITIONS)
    for repeat in range(repeats):
        for name in (names if repeat % 2 == 0 else names[::-1]):
            env, _ = child_environment(CONDITIONS[name])
            with tempfile.TemporaryDirectory(prefix="radspeed-sonnet-") as directory:
                _, record = run_process("You are terse.", {"role": "user", "content": "Reply with OK."}, env, directory)
            record.pop("raw_text", None)
            rows.append(dict(record, condition=name, repeat=repeat))
    return rows


def persistent_probe():
    """Two turns in one process: demonstrates that history carries into turn 2."""
    env, _ = child_environment(CONDITIONS["cli_lean"])
    with tempfile.TemporaryDirectory(prefix="radspeed-sonnet-") as directory:
        process = subprocess.Popen(base_command("You are terse."), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, cwd=directory, env=env)
        results = []
        done = threading.Event()

        def read():
            for line in process.stdout:
                event = json.loads(line)
                if event.get("type") == "result":
                    usage = event.get("usage", {})
                    results.append({
                        "result": event.get("result"), "duration_api_ms": event.get("duration_api_ms"),
                        "input_tokens": usage.get("input_tokens"),
                        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                        "thinking_tokens": usage.get("output_tokens_details", {}).get("thinking_tokens"),
                    })
                    done.set()

        reader = threading.Thread(target=read)
        reader.start()
        for text in ("Reply with OK.", "What did I ask you previously? Answer in six words."):
            done.clear()
            process.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
            process.stdin.flush()
            done.wait(60)
        process.stdin.close()
        reader.join(30)
        process.wait(timeout=30)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--floor-repeats", type=int, default=5)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    os.chdir(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "results.json"
    auth = auth_summary()
    if not auth["loggedIn"] or auth["authMethod"] != "claude.ai" or auth["subscriptionType"] != "max":
        raise RuntimeError("The existing Claude Max subscription session is required")
    from config.config import config
    from llm import format as report_format, impressions, worksheet
    config.SELECTED_MODEL = MODEL
    clients = {name: SubscriptionClient(name, env) for name, env in CONDITIONS.items()}
    active = {"client": clients["cli_default"]}
    for module in (report_format, impressions, worksheet):
        module.get_text_client = lambda *unused: active["client"]

    previous = json.loads(output.read_text()) if output.exists() else {}
    rows = [r for r in previous.get("rows", []) if not r.get("error")]
    failed = previous.get("failed_attempts", []) + [r for r in previous.get("rows", []) if r.get("error")]
    done_keys = {(r["condition"], r["task"], r["case_id"], r["repeat"]) for r in rows}
    payload = {
        "model": MODEL, "auth": auth, "provider": "Claude Code firstParty, subscription only",
        "effort": "low", "repeats": args.repeats, "conditions": {k: sorted(v) for k, v in CONDITIONS.items()},
        "child_environment_overrides_removed": clients["cli_default"].removed_env_count,
        "production_settings_changed": False, "sol_calls_repeated": False,
        "floor_probe": previous.get("floor_probe"), "persistent_probe": previous.get("persistent_probe"),
        "rows": rows, "failed_attempts": failed,
    }

    def save():
        payload["summary"] = summarise(rows)
        output.write_text(json.dumps(payload, indent=2))

    if payload["floor_probe"] is None:
        payload["floor_probe"] = floor_probe(args.floor_repeats)
        save()
    if payload["persistent_probe"] is None:
        payload["persistent_probe"] = persistent_probe()
        save()

    def measure(condition, task, case_id, repeat, function, check=None):
        key = (condition, task, case_id, repeat)
        if key in done_keys:
            return
        client = active["client"] = clients[condition]
        start_index = len(client.calls)
        row = {"model": MODEL, "condition": condition, "task": task, "case_id": case_id, "repeat": repeat}
        started = time.perf_counter()
        first = None
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
        calls = client.calls[start_index:]
        row["calls"] = calls
        row["provider_seconds"] = sum(c.get("provider_seconds", 0) for c in calls)
        row["startup_seconds"] = sum(c.get("init_seconds", 0) for c in calls)
        row["teardown_seconds"] = sum(c.get("exit_seconds", 0) - c.get("result_seconds", 0) for c in calls)
        row["request_window_seconds"] = sum(c.get("result_seconds", 0) - c.get("init_seconds", 0) for c in calls)
        row["release_seconds"] = row["seconds"] - row["teardown_seconds"]
        rows.append(row)
        save()
        print(json.dumps({k: row.get(k) for k in ("condition", "task", "case_id", "repeat", "seconds", "provider_seconds", "error")}), flush=True)

    cases = load_cases()
    names = list(CONDITIONS)
    worksheet_template = report_format._get_template_content("Ultrasound_Worksheet.txt")
    for repeat in range(args.repeats):
        units = []
        for case in cases:
            units.append(("report", case["id"], case))
            if case["id"] in IMPRESSION_CASES:
                units.append(("impression", case["id"], case))
        for name in ("renal", "obstetric"):
            units += [("worksheet_one_step", name, None), ("worksheet_two_step", name, None)]
        for index, (task, case_id, case) in enumerate(units):
            order = names if (repeat + index) % 2 == 0 else names[::-1]
            for condition in order:
                if task == "report":
                    template = report_format._get_template_content(case["template"])
                    measure(condition, task, case_id, repeat,
                            lambda: report_format.stream_format_text(case["transcript"], template_content=template), case)
                elif task == "impression":
                    check = dict(case, section_order=["impression"], measurements=[], laterality=case["laterality"][:1])
                    if case_id == "mri_knee_medial_meniscus":
                        check["required_any"] = case["required_any"][:2]
                    measure(condition, task, case_id, repeat,
                            lambda: impressions.stream_impression(case["transcript"], modality=case["template"], with_guidelines=True), check)
                else:
                    images = worksheet.validate_worksheet_images(
                        [(ROOT / "web/static/reports/worksheet-speed-2026-09-24" / f"{case_id}.png").read_bytes()])
                    if task == "worksheet_one_step":
                        measure(condition, task, case_id, repeat,
                                lambda: worksheet.draft_worksheet_report(images, template_content=worksheet_template, reasoning_effort="low"))
                    else:
                        def two_step():
                            notes = worksheet.extract_worksheet_findings(images)
                            report = report_format.postprocess_report("".join(report_format.stream_format_text(
                                notes, template_content=worksheet_template, source_kind="worksheet")))
                            return worksheet.WorksheetDraft(source_notes=notes, report=report)
                        measure(condition, task, case_id, repeat, two_step)
    payload["auth_after"] = auth_summary()
    payload["complete"] = True
    save()
    return int(any(r.get("error") for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
