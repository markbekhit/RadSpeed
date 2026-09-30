"""Write every generated synthetic draft and automated review flags. Flags are not clinical accuracy."""
from __future__ import annotations

import difflib
import json
from pathlib import Path
import re

from evals.clinical_quality import load_cases
from llm import format as report_format

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/sonnet-reassessment-2026-10-01"

WORKSHEET_FACTS = {
    "renal": {
        "measurements": ["10.8 cm", "10.2 cm", "14 mm", "12 mm", "9 mm", "6 mm", "2.1 × 1.7 × 1.5 cm", "318 mL", "24 mL", "3 mm", "36 mL"],
        "side_bindings": [r"right[^.\n]{0,60}10\.8", r"left[^.\n]{0,60}10\.2", r"right[^.\n]{0,60}14 mm", r"left[^.\n]{0,60}12 mm",
                          r"left[^.\n]{0,80}(?:pelvi|pelvic)[^.\n]{0,60}9 mm|left[^.\n]{0,100}9 mm",
                          r"left[^.\n]{0,80}6 mm|6 mm[^.\n]{0,80}left", r"right[^.\n]{0,80}2\.1|2\.1[^.\n]{0,80}right"],
        "unchecked_leak": [r"acute renal failure", r"haematuria", r"urinary tract infection", r"hematuria"],
        "unsupported_normal": [r"echogenic", r"corticomedullary", r"hydronephrosis", r"normal (?:renal )?(?:parenchyma|morphology|size)",
                               r"normal bladder", r"no (?:perinephric|collection)", r"unremarkable", r"normal"],
    },
    "obstetric": {
        "measurements": ["52 mm", "190 mm", "166 mm", "35 mm", "432 g", "55th", "48th", "57th", "42nd", "51st", "6.2 mm", "148", "3.6 cm", "21 weeks 3 days"],
        "side_bindings": [r"left[^.\n]{0,80}6\.2|6\.2[^.\n]{0,80}left"],
        "unchecked_leak": [],
        "unsupported_normal": [r"liquor", r"amniotic", r"fetal movement", r"right (?:renal|kidney)", r"bladder", r"stomach", r"cord", r"appropriate for", r"consistent with (?:dates|gestation)",
                              r"normal growth", r"normal"],
    },
}
COMMON_PATTERNS = {
    "bp_shortened": r"\bBP\b(?!D)",
    "bpd_present": r"\bBPD\b",
    "repeat_imaging": r"repeat|re-?scan|follow[- ]?up|further imaging",
    "rvot_limitation": r"RVOT[^.\n]{0,160}(?:not well seen|not adequately|not visuali[sz]ed|limited|suboptimal)|(?:not well seen|not adequately|not visuali[sz]ed)[^.\n]{0,60}RVOT",
    "lip_limitation": r"(?:lip|face)[^.\n]{0,160}(?:not well seen|not adequately|not visuali[sz]ed|limited|suboptimal)|(?:not well seen|not adequately|not visuali[sz]ed)[^.\n]{0,60}(?:lip|face)",
}
INTERPRETIVE = r"recommend|suggest|consider|correlat|follow[- ]?up|hypertension|echocardio|likely|consistent with|suspect|differential|appropriate for|clinical(?:ly)? (?:significance|correlation)"


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [re.sub(r"[*#\-•]+", " ", p).strip() for p in parts if re.sub(r"[*#\-•\s:]+", "", p)]


def novel_sentences(row, case, template):
    known = sentences(template) + sentences(case["transcript"])
    out = []
    for sentence in sentences(row["report"]):
        best = max((difflib.SequenceMatcher(None, sentence.lower(), k.lower()).ratio() for k in known), default=0)
        if best < 0.72:
            out.append(sentence)
    return out


def main():
    data = json.loads((OUT / "results.json").read_text())
    rows = [r for r in data["rows"] if not r.get("error")]
    cases = {c["id"]: c for c in load_cases()}
    markdown = ["# Generated synthetic drafts\n", "Model: claude-sonnet-5-5 through Claude Code subscription. Synthetic inputs only.\n"]
    flags = []
    for row in sorted(rows, key=lambda r: (r["task"], r["case_id"], r["repeat"], r["condition"])):
        markdown.append(f"\n## {row['task']} / {row['case_id']} / repeat {row['repeat'] + 1} / {row['condition']}\n")
        if row.get("source_notes"):
            markdown.append("### Source notes\n\n```\n" + row["source_notes"] + "\n```\n")
        markdown.append("### Draft\n\n" + row["report"] + "\n")
        entry = {"condition": row["condition"], "task": row["task"], "case_id": row["case_id"], "repeat": row["repeat"]}
        if row["task"].startswith("worksheet"):
            facts = WORKSHEET_FACTS[row["case_id"]]
            report, notes = row["report"], row.get("source_notes", "")
            both = report + "\n" + notes
            entry["missing_measurements_report"] = [m for m in facts["measurements"] if not _contains(report, m)]
            entry["missing_measurements_notes"] = [m for m in facts["measurements"] if not _contains(notes, m)]
            entry["failed_side_bindings_report"] = [p for p in facts["side_bindings"] if not re.search(p, report, re.I)]
            entry["failed_side_bindings_notes"] = [p for p in facts["side_bindings"] if not re.search(p, notes, re.I)]
            entry["unchecked_option_mentions_notes"] = [p for p in facts["unchecked_leak"] if re.search(p, notes, re.I)]
            entry["unchecked_option_mentions_report"] = [p for p in facts["unchecked_leak"] if re.search(p, report, re.I)]
            entry["normal_or_unsupported_keyword_lines"] = [
                s for s in sentences(report) if any(re.search(p, s, re.I) for p in facts["unsupported_normal"])]
            entry["pattern_hits_report"] = {k: bool(re.search(p, report, re.I)) for k, p in COMMON_PATTERNS.items()}
            entry["pattern_hits_notes"] = {k: bool(re.search(p, notes, re.I)) for k, p in COMMON_PATTERNS.items()}
            impression = re.split(r"\*\*IMPRESSION:?\*\*:?", report, flags=re.I)[-1]
            entry["impression"] = impression.strip()
        else:
            case = cases[row["case_id"]]
            template = report_format._get_template_content(case["template"])
            entry["sentences_not_in_dictation_or_template"] = novel_sentences(row, case, template)
            entry["interpretive_lines"] = [s for s in sentences(row["report"]) if re.search(INTERPRETIVE, s, re.I)]
            dictated_numbers = set(re.findall(r"\d+(?:\.\d+)?", case["transcript"]))
            entry["numbers_not_dictated"] = sorted(set(re.findall(r"\d+(?:\.\d+)?", row["report"])) - dictated_numbers)
        flags.append(entry)
    (OUT / "generated-drafts.md").write_text("\n".join(markdown))
    (OUT / "automated-review-flags.json").write_text(json.dumps(flags, indent=2))
    print(len(rows), "drafts written")


def _contains(text, measurement):
    normalised = re.sub(r"\s+", " ", text.replace("×", "x").replace("x", "x")).lower()
    target = measurement.replace("×", "x").lower()
    if target in normalised:
        return True
    return target.replace(" ", "") in normalised.replace(" ", "")


if __name__ == "__main__":
    main()
