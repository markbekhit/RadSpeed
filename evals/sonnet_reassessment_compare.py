"""Compare saved Sol timings with the Sonnet subscription reassessment; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/sonnet-reassessment-2026-10-01"
TASKS = ("report", "impression", "worksheet_one_step", "worksheet_two_step")


def med(values):
    values = list(values)
    return round(statistics.median(values), 2) if values else None


def sol_medians():
    sources = {
        "gpt-6-sol": {}, "gpt-6.1-sol": {},
    }
    for name in ("model-comparison-2026-09-30", "worksheet-model-comparison-2026-09-30"):
        rows = json.loads((ROOT / "reports" / name / "results.json").read_text())["rows"]
        for row in rows:
            if row["task"] in TASKS and not row.get("error"):
                sources[row["model"]].setdefault(row["task"], []).append(row["seconds"])
    return {model: {task: {"n": len(v), "median_total_seconds": med(v)} for task, v in tasks.items()}
            for model, tasks in sources.items()}


def text_size(row):
    return len(row.get("report") or "") + len(row.get("source_notes") or "")


def detail(rows):
    out = {}
    for condition in sorted({r["condition"] for r in rows}):
        for task in TASKS:
            group = [r for r in rows if r["condition"] == condition and r["task"] == task]
            calls = [c for r in group for c in r["calls"]]
            out[f"{condition}:{task}"] = {
                "total_seconds_min_max": [round(min(r["seconds"] for r in group), 2), round(max(r["seconds"] for r in group), 2)],
                "release_seconds_min_max": [round(min(r["release_seconds"] for r in group), 2), round(max(r["release_seconds"] for r in group), 2)],
                "calls_with_thinking": sum((c["usage"].get("thinking_tokens") or 0) > 0 for c in calls),
                "calls": len(calls),
                "median_generated_characters": med(text_size(r) for r in group),
                "median_output_tokens_per_second_in_request_window": med(
                    sum(c["usage"]["output_tokens"] for c in r["calls"]) / r["request_window_seconds"] for r in group),
            }
    return out


def sol_detail():
    out = {}
    for name in ("model-comparison-2026-09-30", "worksheet-model-comparison-2026-09-30"):
        rows = json.loads((ROOT / "reports" / name / "results.json").read_text())["rows"]
        for model in ("gpt-6-sol", "gpt-6.1-sol"):
            for task in TASKS:
                group = [r for r in rows if r["task"] == task and r["model"] == model and not r.get("error")]
                if group:
                    usage = [c.get("usage", {}) for r in group for c in r.get("api_calls", [])]
                    out[f"{model}:{task}"] = {
                        "n": len(group),
                        "total_seconds_min_max": [round(min(r["seconds"] for r in group), 2), round(max(r["seconds"] for r in group), 2)],
                        "median_first_text_seconds": med(r["first_text_seconds"] for r in group if r.get("first_text_seconds") is not None) if any(r.get("first_text_seconds") is not None for r in group) else None,
                        "median_generated_characters": med(text_size(r) for r in group),
                        "median_completion_tokens_per_row": med(sum(u.get("completion_tokens", 0) for u in [c.get("usage", {}) for c in r.get("api_calls", [])]) for r in group) if usage else None,
                    }
    return out


def main():
    data = json.loads((OUT / "results.json").read_text())
    rows = [r for r in data["rows"] if not r.get("error")]
    table = {"sol": sol_medians(), "sonnet": {}, "sonnet_by_worksheet": {}, "cache": {}, "floor": {}}
    metrics = {
        "total_to_exit": "seconds", "release": "release_seconds", "request_window": "request_window_seconds",
        "provider_reported": "provider_seconds", "startup": "startup_seconds", "teardown": "teardown_seconds",
    }
    for condition in sorted({r["condition"] for r in rows}):
        for task in TASKS:
            group = [r for r in rows if r["condition"] == condition and r["task"] == task]
            table["sonnet"].setdefault(condition, {})[task] = {
                "n": len(group), **{k: med(r[v] for r in group) for k, v in metrics.items()},
                "first_text": med(r["first_text_seconds"] for r in group if r["first_text_seconds"] is not None),
                "underlying_calls": med(len(r["calls"]) for r in group),
                "output_tokens": med(sum(c["usage"]["output_tokens"] for c in r["calls"]) for r in group),
                "input_tokens_total": med(sum(sum(c["usage"][k] or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) for c in r["calls"]) for r in group),
                "cache_read_share": med(
                    sum(c["usage"]["cache_read_input_tokens"] or 0 for c in r["calls"])
                    / max(1, sum(sum(c["usage"][k] or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) for c in r["calls"]))
                    for r in group),
                "thinking_tokens": sum(c["usage"].get("thinking_tokens") or 0 for r in group for c in r["calls"]),
                "outer_json_fences_removed": sum(bool(c.get("outer_json_fence_removed")) for r in group for c in r["calls"]),
            }
        for name in ("renal", "obstetric"):
            for task in TASKS[2:]:
                group = [r for r in rows if r["condition"] == condition and r["task"] == task and r["case_id"] == name]
                table["sonnet_by_worksheet"].setdefault(condition, {})[f"{task}:{name}"] = {
                    "n": len(group), **{k: med(r[v] for r in group) for k, v in metrics.items()}}
        for repeat in range(3):
            group = [r for r in rows if r["condition"] == condition and r["repeat"] == repeat]
            calls = [c for r in group for c in r["calls"]]
            table["cache"].setdefault(condition, {})[f"repeat_{repeat}"] = {
                "calls": len(calls),
                "calls_with_cache_read": sum((c["usage"]["cache_read_input_tokens"] or 0) > 0 for c in calls),
                "median_provider_seconds_per_call": med(c["provider_seconds"] for c in calls),
            }
    floor = data["floor_probe"]
    for condition in sorted({r["condition"] for r in floor}):
        group = [r for r in floor if r["condition"] == condition]
        table["floor"][condition] = {
            "n": len(group), "init": med(r["init_seconds"] for r in group),
            "message_start": med(r["message_start_seconds"] for r in group),
            "result": med(r["result_seconds"] for r in group), "exit": med(r["exit_seconds"] for r in group),
            "provider_reported": med(r["provider_seconds"] for r in group),
        }
    table["persistent_probe"] = data["persistent_probe"]
    table["detail"] = detail(rows)
    table["sol_detail"] = sol_detail()
    (OUT / "comparison.json").write_text(json.dumps(table, indent=2))
    print(json.dumps({k: table[k] for k in ("detail", "sol_detail")}, indent=1))


if __name__ == "__main__":
    main()
