"""Rule-based quality gate for synthetic radiology report cases.

The checks deliberately avoid requiring one exact model phrasing. They protect
clinical facts that must survive formatting: key findings, negation, laterality,
measurements, and section order. ``--live`` calls the configured production text
model; the default mode evaluates the reviewed reference reports and validates
the corpus/evaluator without network access.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


CASES_PATH = Path(__file__).with_name("clinical_cases.json")


def _normalise(text: str) -> str:
    text = text.lower().replace("×", "x")
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    safety_critical: bool = False


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    score: float
    checks: list[Check]
    report: str


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        cases = json.load(handle)
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Clinical eval case IDs must be unique")
    return cases


def evaluate_case(case: dict, report: str) -> CaseResult:
    normalised = _normalise(report or "")
    checks: list[Check] = []

    for index, alternatives in enumerate(case.get("required_any", []), start=1):
        found = any(_normalise(term) in normalised for term in alternatives)
        checks.append(
            Check(
                name=f"required_concept_{index}",
                passed=found,
                detail="one of: " + " | ".join(alternatives),
                safety_critical=True,
            )
        )

    for phrase in case.get("forbidden", []):
        absent = _normalise(phrase) not in normalised
        checks.append(
            Check(
                name=f"forbidden:{phrase}",
                passed=absent,
                detail="must not appear",
                safety_critical=True,
            )
        )

    for measurement in case.get("measurements", []):
        present = _normalise(measurement) in normalised
        checks.append(
            Check(
                name=f"measurement:{measurement}",
                passed=present,
                detail="dictated measurement must be preserved",
                safety_critical=True,
            )
        )

    for side in case.get("laterality", []):
        present = re.search(rf"\b{re.escape(side.lower())}\b", normalised) is not None
        checks.append(
            Check(
                name=f"laterality:{side}",
                passed=present,
                detail="dictated laterality must be preserved",
                safety_critical=True,
            )
        )

    section_positions = []
    for section in case.get("section_order", []):
        match = re.search(rf"\b{re.escape(section.lower())}\b", normalised)
        section_positions.append(match.start() if match else -1)
    sections_valid = bool(section_positions) and all(pos >= 0 for pos in section_positions)
    sections_valid = sections_valid and section_positions == sorted(section_positions)
    checks.append(
        Check(
            name="section_order",
            passed=sections_valid,
            detail=" → ".join(case.get("section_order", [])),
        )
    )

    passed_count = sum(check.passed for check in checks)
    score = passed_count / len(checks) if checks else 0.0
    safety_ok = all(check.passed for check in checks if check.safety_critical)
    return CaseResult(
        case_id=case["id"],
        passed=safety_ok and score >= 0.9,
        score=score,
        checks=checks,
        report=report or "",
    )


def evaluate_suite(cases: Iterable[dict], reports: dict[str, str]) -> list[CaseResult]:
    return [evaluate_case(case, reports.get(case["id"], "")) for case in cases]


def _live_reports(cases: list[dict]) -> dict[str, str]:
    from config.config import config
    from config.settings import load_settings
    from llm.format import _create_structured_report, _get_template_content

    load_settings(web_mode=True)
    if not config.TEXT_API_KEY:
        raise RuntimeError("No text-model API key is configured for live clinical evals")

    reports = {}
    for case in cases:
        template = _get_template_content(case["template"])
        if not template:
            raise RuntimeError(f"Template not found: {case['template']}")
        reports[case["id"]] = _create_structured_report(case["transcript"], template) or ""
    return reports


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate RadSpeed on synthetic clinical cases")
    parser.add_argument("--live", action="store_true", help="Generate reports with the configured text model")
    parser.add_argument("--responses", type=Path, help="JSON object mapping case IDs to candidate reports")
    parser.add_argument("--output", type=Path, help="Write detailed JSON results to this path")
    parser.add_argument("--minimum-pass-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    cases = load_cases()
    if args.live and args.responses:
        parser.error("Choose either --live or --responses")
    if args.live:
        reports = _live_reports(cases)
        mode = "live"
    elif args.responses:
        reports = json.loads(args.responses.read_text(encoding="utf-8"))
        mode = "responses"
    else:
        reports = {case["id"]: case["reference_report"] for case in cases}
        mode = "references"

    results = evaluate_suite(cases, reports)
    passed = sum(result.passed for result in results)
    pass_rate = passed / len(results) if results else 0.0
    payload = {
        "mode": mode,
        "summary": {"passed": passed, "total": len(results), "pass_rate": pass_rate},
        "results": [asdict(result) for result in results],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Clinical eval ({mode}): {passed}/{len(results)} cases passed ({pass_rate:.0%})")
    for result in results:
        failures = [check.name for check in result.checks if not check.passed]
        print(f"  {'PASS' if result.passed else 'FAIL'} {result.case_id}: {result.score:.0%}", end="")
        if failures:
            print(" — " + ", ".join(failures))
        else:
            print()
    return 0 if pass_rate >= args.minimum_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
