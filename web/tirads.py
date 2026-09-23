"""ACR TI-RADS 2017 thyroid nodule risk stratification.

Pure, deterministic scoring for the public calculator. No patient data is
stored or sent to any model; the calculator works on ultrasound feature
selections only. This module is the single source of truth for the scoring
rules — the web API and tests both call it.

Source: Tessler FN et al. "ACR Thyroid Imaging, Reporting and Data System
(TI-RADS): White Paper of the ACR TI-RADS Committee." J Am Coll Radiol 2017.
Point values, category bands and management thresholds follow that white paper,
including its chart notes (spongiform nodules take no further points; composition
that cannot be determined scores 2, echogenicity 1 and margin 0) and its
definition of significant enlargement on follow-up.
"""

from __future__ import annotations

from typing import Optional

# Each feature maps an option key to (human label, ACR points).
COMPOSITION: dict[str, tuple[str, int]] = {
    "cystic": ("Cystic or almost completely cystic", 0),
    "spongiform": ("Spongiform", 0),
    "mixed": ("Mixed cystic and solid", 1),
    "solid": ("Solid or almost completely solid", 2),
    "indeterminate": ("Cannot be determined because of calcification", 2),
}

ECHOGENICITY: dict[str, tuple[str, int]] = {
    "anechoic": ("Anechoic", 0),
    "iso_hyper": ("Hyperechoic or isoechoic", 1),
    "hypo": ("Hypoechoic", 2),
    "very_hypo": ("Very hypoechoic", 3),
    "indeterminate": ("Cannot be determined", 1),
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
    "indeterminate": ("Cannot be determined", 0),
}

# Echogenic foci are additive — a nodule can have several. "none" scores 0 and
# is mutually exclusive with the others in the UI, but is ignored if combined.
FOCI: dict[str, tuple[str, int]] = {
    "none": ("None or large comet-tail artifacts", 0),
    "macro": ("Macrocalcifications", 1),
    "rim": ("Peripheral (rim) calcifications", 2),
    "punctate": ("Punctate echogenic foci", 3),
}

# Report-line phrasing where the chart label does not read well in a sentence.
_COMPOSITION_REPORT: dict[str, str] = {
    "indeterminate": "composition obscured by calcification",
}
_ECHOGENICITY_REPORT: dict[str, str] = {
    "indeterminate": "echogenicity not assessable",
}
_MARGIN_REPORT: dict[str, str] = {
    "indeterminate": "margin not assessable",
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


# Significant enlargement (white paper, "Definition of Growth"): a 20% increase
# in at least two dimensions with a minimal increase of 2 mm, or a 50% or
# greater increase in volume. Each qualifying dimension must meet both the
# percentage and the 2 mm floor.
GROWTH_DIMENSION_PERCENT = 20.0
GROWTH_DIMENSION_MIN_MM = 2.0
GROWTH_VOLUME_PERCENT = 50.0

_LEVEL_ORDER = ["TR1", "TR2", "TR3", "TR4", "TR5"]


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


def _clean_dims(dims, field: str) -> list[float]:
    """Return up to three positive dimensions in millimetres, in entry order."""
    cleaned: list[float] = []
    for value in list(dims or []):
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be numbers in millimetres")
        if number > 0:
            cleaned.append(number)
    if len(cleaned) > 3:
        raise ValueError(f"{field} accepts at most three dimensions")
    return cleaned


def _ellipsoid_volume_mm3(dims: list[float]) -> float:
    a, b, c = dims
    return 3.141592653589793 / 6 * a * b * c


def compare_prior(current_dims, prior_dims) -> Optional[dict]:
    """Classify interval change against the ACR significant-enlargement rule.

    Dimensions are compared position by position, so enter them in the same
    order on both studies. Volume uses the ellipsoid formula and needs all
    three dimensions on both studies. Returns None when either study has no
    usable measurement.
    """
    current = _clean_dims(current_dims, "Current dimensions")
    prior = _clean_dims(prior_dims, "Prior dimensions")
    if not current or not prior:
        return None
    if len(current) != len(prior):
        raise ValueError("Enter the same number of dimensions for the current and prior study")

    dimension_changes = []
    qualifying = 0
    for now, before in zip(current, prior):
        change_mm = now - before
        change_percent = change_mm / before * 100
        meets = change_percent >= GROWTH_DIMENSION_PERCENT and change_mm >= GROWTH_DIMENSION_MIN_MM
        if meets:
            qualifying += 1
        dimension_changes.append({
            "prior_mm": before,
            "current_mm": now,
            "change_mm": round(change_mm, 1),
            "change_percent": round(change_percent, 1),
            "meets_threshold": meets,
        })

    volume_change_percent = None
    if len(current) == 3:
        before_volume = _ellipsoid_volume_mm3(prior)
        now_volume = _ellipsoid_volume_mm3(current)
        volume_change_percent = round((now_volume - before_volume) / before_volume * 100, 1)

    by_dimensions = qualifying >= 2
    by_volume = volume_change_percent is not None and volume_change_percent >= GROWTH_VOLUME_PERCENT
    significant = by_dimensions or by_volume

    if significant:
        reasons = []
        if by_dimensions:
            reasons.append(f"≥20% and ≥2 mm in {qualifying} dimensions")
        if by_volume:
            reasons.append(f"volume +{volume_change_percent:g}%")
        summary = "Significant enlargement by ACR TI-RADS criteria (" + "; ".join(reasons) + ")."
    elif all(d["change_mm"] <= 0 for d in dimension_changes):
        summary = "No interval enlargement."
    else:
        summary = "Interval change below the ACR TI-RADS threshold for significant enlargement."
        if volume_change_percent is not None:
            summary = summary[:-1] + f" (volume {volume_change_percent:+g}%)."

    return {
        "significant_enlargement": significant,
        "qualifying_dimensions": qualifying,
        "volume_change_percent": volume_change_percent,
        "dimensions": dimension_changes,
        "prior_dims_mm": prior,
        "summary": summary,
    }


def _schedule(intervals: str) -> str:
    """Phrase an interval schedule after a verb: 'at 1, 3 and 5 years' or 'annually ...'."""
    return intervals if intervals.startswith("annually") else f"at {intervals}"


def _management(level: str, size_mm: Optional[float], enlarged: bool = False) -> str:
    meta = LEVELS[level]
    fna_cm = meta["fna_cm"]
    follow_cm = meta["follow_cm"]

    if fna_cm is None:
        return "No FNA or follow-up ultrasound indicated."

    if size_mm is None:
        return (
            f"FNA if ≥{_fmt_cm(fna_cm)} cm; follow-up ultrasound if "
            f"≥{_fmt_cm(follow_cm)} cm ({_schedule(meta['intervals'])})."
        )

    size_cm = size_mm / 10.0
    if size_cm >= fna_cm:
        return "FNA recommended."
    if size_cm >= follow_cm:
        advice = f"Follow-up ultrasound recommended {_schedule(meta['intervals'])}."
        if not enlarged:
            advice += " Imaging can stop at 5 years if the size is unchanged."
        return advice
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
    dims_mm: Optional[list[float]] = None,
    comparison: Optional[dict] = None,
) -> str:
    """Build a paste-ready structured report sentence for the findings block."""
    comp_label = _COMPOSITION_REPORT.get(composition, COMPOSITION[composition][0].lower())
    echo_label = _ECHOGENICITY_REPORT.get(echogenicity, ECHOGENICITY[echogenicity][0].lower())
    shape_label = SHAPE[shape][0].lower()
    margin_label = _MARGIN_REPORT.get(margin, MARGIN[margin][0].lower() + " margin")

    if foci_keys:
        foci_label = " and ".join(_FOCI_REPORT[k] for k in foci_keys)
        foci_clause = f"with {foci_label}"
    else:
        foci_clause = "with no suspicious echogenic foci"

    loc = (location or "").strip()
    lead = f"{loc} thyroid nodule" if loc else "Thyroid nodule"
    if dims_mm and len(dims_mm) > 1:
        lead += f" measuring {_fmt_dims(dims_mm)}"
    elif size_mm is not None:
        lead += f" measuring {_fmt_size(size_mm)}"

    if composition == "spongiform":
        descriptors = "spongiform (no further points assigned)"
    else:
        descriptors = f"{comp_label}, {echo_label}, {shape_label}, {margin_label}, {foci_clause}"
    line = f"{lead}: {descriptors}. "
    if comparison:
        line += f"Previously {_fmt_dims(comparison['prior_dims_mm'])}. {comparison['summary']} "
    return (
        line
        + f"ACR TI-RADS {points} point{'s' if points != 1 else ''} — "
        f"{level} ({LEVELS[level]['label'].lower()}). {management}"
    )


def _fmt_dims(dims_mm: list[float]) -> str:
    """Format dimensions in one unit: cm when the largest is 10 mm or more."""
    if max(dims_mm) >= 10:
        return " × ".join(f"{round(d / 10.0, 2):g}" for d in dims_mm) + " cm"
    return " × ".join(f"{round(d, 1):g}" for d in dims_mm) + " mm"


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
    dims_mm: Optional[list[float]] = None,
    prior_dims_mm: Optional[list[float]] = None,
    prior_level: Optional[str] = None,
) -> dict:
    """Score a thyroid nodule and return a JSON-serialisable result.

    Raises ValueError on an unknown option key. `size_mm` and `location` are
    optional; when omitted the management text gives the size thresholds
    instead of a single recommendation. `dims_mm` (up to three dimensions)
    supplies the maximum diameter when `size_mm` is absent. `prior_dims_mm`
    adds the ACR significant-enlargement check, and `prior_level` flags a TR
    level increase, which ACR follows with a sonogram in 1 year.
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

    dims = _clean_dims(dims_mm, "Current dimensions")
    if size_mm is None and dims:
        size_mm = max(dims)

    if prior_level is not None and prior_level not in LEVELS:
        valid = ", ".join(LEVELS)
        raise ValueError(f"Unknown prior level {prior_level!r}. Expected one of: {valid}")

    # Chart note: spongiform nodules take no further points, and small
    # echogenic foci in them are the back walls of minute cysts.
    if composition == "spongiform":
        echo_pts = shape_pts = margin_pts = foci_pts = 0
        foci_selected = []

    points = comp_pts + echo_pts + shape_pts + margin_pts + foci_pts
    level = level_for_points(points)
    meta = LEVELS[level]
    comparison = compare_prior(dims, prior_dims_mm) if prior_dims_mm else None
    enlarged = bool(comparison and comparison["significant_enlargement"])
    management = _management(level, size_mm, enlarged)

    notes: list[str] = []
    level_increased = (
        prior_level is not None
        and _LEVEL_ORDER.index(level) > _LEVEL_ORDER.index(prior_level)
    )
    if level_increased:
        management += (
            f" TR level has increased from {prior_level}; ACR advises the next"
            " sonogram in 1 year, regardless of the initial level."
        )
    if enlarged and meta["fna_cm"] is not None:
        if size_mm is not None and size_mm / 10.0 < meta["fna_cm"]:
            notes.append(
                "The nodule has enlarged significantly but remains below the FNA size"
                " threshold. ACR has no evidence-based rule here; continued follow-up is"
                " probably warranted."
            )
    if level == "TR5" and size_mm is not None and 5 <= size_mm < 10:
        notes.append(
            "FNA of a 5–9 mm TR5 nodule may be appropriate after shared decision-making."
            " State whether the nodule can be measured reproducibly and whether it abuts"
            " the trachea or the tracheoesophageal groove."
        )
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
        dims_mm=dims,
        comparison=comparison,
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
        "size_mm": size_mm,
        "comparison": comparison,
        "level_increased": level_increased,
        "notes": notes,
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
