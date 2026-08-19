"""ACR TI-RADS 2017 thyroid nodule risk stratification.

Pure, deterministic scoring for the public calculator. No patient data is
stored or sent to any model; the calculator works on ultrasound feature
selections only. This module is the single source of truth for the scoring
rules — the web API and tests both call it.

Source: Tessler FN et al. "ACR Thyroid Imaging, Reporting and Data System
(TI-RADS): White Paper of the ACR TI-RADS Committee." J Am Coll Radiol 2017.
Point values, category bands and management thresholds follow that white paper.
"""

from __future__ import annotations

from typing import Optional

# Each feature maps an option key to (human label, ACR points).
COMPOSITION: dict[str, tuple[str, int]] = {
    "cystic": ("Cystic or almost completely cystic", 0),
    "spongiform": ("Spongiform", 0),
    "mixed": ("Mixed cystic and solid", 1),
    "solid": ("Solid or almost completely solid", 2),
}

ECHOGENICITY: dict[str, tuple[str, int]] = {
    "anechoic": ("Anechoic", 0),
    "iso_hyper": ("Hyperechoic or isoechoic", 1),
    "hypo": ("Hypoechoic", 2),
    "very_hypo": ("Very hypoechoic", 3),
}

SHAPE: dict[str, tuple[str, int]] = {
    "wider": ("Wider-than-tall", 0),
    "taller": ("Taller-than-wide", 3),
}

MARGIN: dict[str, tuple[str, int]] = {
    "smooth": ("Smooth", 0),
    "ill_defined": ("Ill-defined", 0),
    "lobulated": ("Lobulated or irregular", 2),
    "ete": ("Extra-thyroidal extension", 3),
}

# Echogenic foci are additive — a nodule can have several. "none" scores 0 and
# is mutually exclusive with the others in the UI, but is ignored if combined.
FOCI: dict[str, tuple[str, int]] = {
    "none": ("None or large comet-tail artifacts", 0),
    "macro": ("Macrocalcifications", 1),
    "rim": ("Peripheral (rim) calcifications", 2),
    "punctate": ("Punctate echogenic foci", 3),
}

# Report-line phrasing for foci (concise, radiologist-facing).
_FOCI_REPORT: dict[str, str] = {
    "macro": "macrocalcification",
    "rim": "peripheral (rim) calcification",
    "punctate": "punctate echogenic foci",
}

# Level metadata keyed by TR level. `risk` is the reported estimated malignancy
# rate from the ACR white paper. `fna_cm` / `follow_cm` are size thresholds in
# centimetres; None means no FNA or follow-up is indicated at any size.
LEVELS: dict[str, dict] = {
    "TR1": {
        "label": "Benign",
        "risk": "0.3%",
        "fna_cm": None,
        "follow_cm": None,
        "intervals": None,
    },
    "TR2": {
        "label": "Not suspicious",
        "risk": "1.5%",
        "fna_cm": None,
        "follow_cm": None,
        "intervals": None,
    },
    "TR3": {
        "label": "Mildly suspicious",
        "risk": "4.8%",
        "fna_cm": 2.5,
        "follow_cm": 1.5,
        "intervals": "1, 3 and 5 years",
    },
    "TR4": {
        "label": "Moderately suspicious",
        "risk": "9.1%",
        "fna_cm": 1.5,
        "follow_cm": 1.0,
        "intervals": "1, 2, 3 and 5 years",
    },
    "TR5": {
        "label": "Highly suspicious",
        "risk": "≥35%",
        "fna_cm": 1.0,
        "follow_cm": 0.5,
        "intervals": "annually for up to 5 years",
    },
}


def level_for_points(points: int) -> str:
    """Map total ACR points to the TR level band.

    0 -> TR1, 1-2 -> TR2, 3 -> TR3, 4-6 -> TR4, 7+ -> TR5.
    """
    if points <= 0:
        return "TR1"
    if points <= 2:
        return "TR2"
    if points == 3:
        return "TR3"
    if points <= 6:
        return "TR4"
    return "TR5"


def _points(table: dict[str, tuple[str, int]], key: str, field: str) -> tuple[str, int]:
    try:
        return table[key]
    except KeyError:
        valid = ", ".join(sorted(table))
        raise ValueError(f"Unknown {field} option {key!r}. Expected one of: {valid}")


def _foci_points(keys: list[str]) -> tuple[list[str], int]:
    """Return (selected non-'none' labels, additive points)."""
    selected: list[str] = []
    total = 0
    for key in keys:
        label, pts = _points(FOCI, key, "echogenic foci")
        if key == "none":
            continue
        selected.append(key)
        total += pts
    return selected, total


def _management(level: str, size_mm: Optional[float]) -> str:
    meta = LEVELS[level]
    fna_cm = meta["fna_cm"]
    follow_cm = meta["follow_cm"]

    if fna_cm is None:
        return "No FNA or follow-up ultrasound indicated."

    if size_mm is None:
        return (
            f"FNA if ≥{_fmt_cm(fna_cm)} cm; follow-up ultrasound if "
            f"≥{_fmt_cm(follow_cm)} cm (at {meta['intervals']})."
        )

    size_cm = size_mm / 10.0
    if size_cm >= fna_cm:
        return "FNA recommended."
    if size_cm >= follow_cm:
        return f"Follow-up ultrasound recommended at {meta['intervals']}."
    return "Below the size threshold for FNA or follow-up ultrasound; no further imaging indicated."


def _fmt_cm(value: float) -> str:
    return f"{value:g}"


def _report_line(
    composition: str,
    echogenicity: str,
    shape: str,
    margin: str,
    foci_keys: list[str],
    points: int,
    level: str,
    management: str,
    size_mm: Optional[float],
    location: Optional[str],
) -> str:
    """Build a paste-ready structured report sentence for the findings block."""
    comp_label = COMPOSITION[composition][0].lower()
    echo_label = ECHOGENICITY[echogenicity][0].lower()
    shape_label = SHAPE[shape][0].lower()
    margin_label = MARGIN[margin][0].lower()

    if foci_keys:
        foci_label = " and ".join(_FOCI_REPORT[k] for k in foci_keys)
        foci_clause = f"with {foci_label}"
    else:
        foci_clause = "with no suspicious echogenic foci"

    loc = (location or "").strip()
    lead = f"{loc} thyroid nodule" if loc else "Thyroid nodule"
    if size_mm is not None:
        lead += f" measuring {_fmt_size(size_mm)}"

    descriptors = f"{comp_label}, {echo_label}, {shape_label}, {margin_label} margin, {foci_clause}"
    return (
        f"{lead}: {descriptors}. "
        f"ACR TI-RADS {points} point{'s' if points != 1 else ''} — "
        f"{level} ({LEVELS[level]['label'].lower()}). {management}"
    )


def _fmt_size(size_mm: float) -> str:
    if size_mm >= 10:
        return f"{_fmt_cm(size_mm / 10.0)} cm"
    return f"{_fmt_cm(size_mm)} mm"


def score(
    composition: str,
    echogenicity: str,
    shape: str,
    margin: str,
    foci: Optional[list[str]] = None,
    size_mm: Optional[float] = None,
    location: Optional[str] = None,
) -> dict:
    """Score a thyroid nodule and return a JSON-serialisable result.

    Raises ValueError on an unknown option key. `size_mm` and `location` are
    optional; when omitted the management text gives the size thresholds
    instead of a single recommendation.
    """
    comp_label, comp_pts = _points(COMPOSITION, composition, "composition")
    echo_label, echo_pts = _points(ECHOGENICITY, echogenicity, "echogenicity")
    shape_label, shape_pts = _points(SHAPE, shape, "shape")
    margin_label, margin_pts = _points(MARGIN, margin, "margin")
    foci_selected, foci_pts = _foci_points(list(foci or []))

    if size_mm is not None:
        try:
            size_mm = float(size_mm)
        except (TypeError, ValueError):
            raise ValueError("size_mm must be a number")
        if size_mm <= 0:
            size_mm = None

    points = comp_pts + echo_pts + shape_pts + margin_pts + foci_pts
    level = level_for_points(points)
    meta = LEVELS[level]
    management = _management(level, size_mm)
    report_line = _report_line(
        composition,
        echogenicity,
        shape,
        margin,
        foci_selected,
        points,
        level,
        management,
        size_mm,
        location,
    )

    return {
        "points": points,
        "level": level,
        "level_label": meta["label"],
        "malignancy_risk": meta["risk"],
        "fna_threshold_cm": meta["fna_cm"],
        "follow_threshold_cm": meta["follow_cm"],
        "follow_intervals": meta["intervals"],
        "management": management,
        "report_line": report_line,
        "breakdown": {
            "composition": {"label": comp_label, "points": comp_pts},
            "echogenicity": {"label": echo_label, "points": echo_pts},
            "shape": {"label": shape_label, "points": shape_pts},
            "margin": {"label": margin_label, "points": margin_pts},
            "echogenic_foci": {
                "labels": [FOCI[k][0] for k in foci_selected] or [FOCI["none"][0]],
                "points": foci_pts,
            },
        },
    }
