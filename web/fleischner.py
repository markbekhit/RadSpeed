"""Fleischner Society 2017 incidental pulmonary nodule follow-up.

Pure, deterministic recommendation logic for the public calculator. No patient
data is stored or sent to any model; the tool works on the nodule descriptors
only. This module is the single source of truth for the rules — the web API and
tests both call it.

Source: MacMahon H, Naidich DP, Goo JM, et al. "Guidelines for Management of
Incidental Pulmonary Nodules Detected on CT Images: From the Fleischner Society
2017." Radiology 2017;284(1):228-243. Size bands, risk split and follow-up
intervals follow that consensus statement.

Scope of the guideline (reproduced here as a boundary, not clinical advice):
solitary or multiple incidental nodules in patients aged 35 years or older. It
does not apply to lung-cancer screening, immunocompromised patients, or patients
with known or suspected primary malignancy.
"""

from __future__ import annotations

from typing import Optional

NODULE_TYPES: dict[str, str] = {
    "solid": "Solid",
    "ground_glass": "Pure ground-glass",
    "part_solid": "Part-solid",
}

RISK_LABELS: dict[str, str] = {
    "low": "low-risk",
    "high": "high-risk",
}

_APPLICABILITY = (
    "Applies to incidental nodules in patients aged 35 or older. Not for "
    "lung-cancer screening, immunocompromised patients, or known or suspected "
    "primary cancer."
)

# Follow-up recommendation text for solid nodules, keyed by
# multiplicity -> size band -> risk. Bands: "lt6" (<6 mm), "6to8" (6-8 mm),
# "gt8" (>8 mm). Wording follows the Fleischner 2017 recommendation table.
_SOLID: dict[str, dict[str, dict[str, str]]] = {
    "single": {
        "lt6": {
            "low": "No routine follow-up is required.",
            "high": "Optional CT at 12 months. Follow up if the nodule has "
            "suspicious morphology or an upper-lobe location.",
        },
        "6to8": {
            "low": "CT at 6–12 months, then consider CT at 18–24 months.",
            "high": "CT at 6–12 months, then CT at 18–24 months.",
        },
        "gt8": {
            "low": "Consider CT at 3 months, PET-CT, or tissue sampling.",
            "high": "Consider CT at 3 months, PET-CT, or tissue sampling.",
        },
    },
    "multiple": {
        "lt6": {
            "low": "No routine follow-up is required.",
            "high": "Optional CT at 12 months. Follow up if a nodule has "
            "suspicious morphology or an upper-lobe location.",
        },
        "6to8": {
            "low": "CT at 3–6 months, then consider CT at 18–24 months.",
            "high": "CT at 3–6 months, then CT at 18–24 months.",
        },
        "gt8": {
            "low": "CT at 3–6 months, then consider CT at 18–24 months.",
            "high": "CT at 3–6 months, then CT at 18–24 months.",
        },
    },
}

# Human labels and CT volume equivalents for the solid size bands.
_SOLID_BAND_META: dict[str, tuple[str, str]] = {
    "lt6": ("<6 mm", "<100 mm³"),
    "6to8": ("6–8 mm", "100–250 mm³"),
    "gt8": (">8 mm", ">250 mm³"),
}

_SUBSOLID_BAND_META: dict[str, str] = {
    "lt6": "<6 mm",
    "ge6": "≥6 mm",
}

# Note appended to every multiple-nodule recommendation.
_MULTIPLE_NOTE = " Base overall management on the most suspicious nodule."


def _solid_band(size_mm: float) -> str:
    if size_mm < 6:
        return "lt6"
    if size_mm <= 8:
        return "6to8"
    return "gt8"


def _subsolid_band(size_mm: float) -> str:
    return "lt6" if size_mm < 6 else "ge6"


def _validate_size(size_mm) -> float:
    try:
        value = float(size_mm)
    except (TypeError, ValueError):
        raise ValueError("size_mm must be a number")
    if value <= 0:
        raise ValueError("size_mm must be greater than 0")
    return value


def _fmt_mm(size_mm: float) -> str:
    return f"{size_mm:g} mm"


def _solid_recommendation(multiple: bool, band: str, risk: str) -> str:
    multiplicity = "multiple" if multiple else "single"
    rec = _SOLID[multiplicity][band][risk]
    if multiple:
        rec += _MULTIPLE_NOTE
    return rec


def _subsolid_recommendation(
    nodule_type: str,
    multiple: bool,
    band: str,
    solid_component_mm: Optional[float],
) -> str:
    # Multiple subsolid nodules share one combined recommendation.
    if multiple:
        if band == "lt6":
            return (
                "CT at 3–6 months. If stable, consider CT at 2 and 4 years."
                + _MULTIPLE_NOTE
            )
        return "CT at 3–6 months, then base management on the most suspicious nodule."

    if nodule_type == "ground_glass":
        if band == "lt6":
            return (
                "No routine follow-up is required. If morphology is suspicious, "
                "consider CT at 2 and 4 years."
            )
        return (
            "CT at 6–12 months to confirm persistence, then CT every 2 years "
            "until 5 years."
        )

    # Single part-solid nodule.
    if band == "lt6":
        return "No routine follow-up is required."
    rec = (
        "CT at 3–6 months to confirm persistence. If unchanged and the solid "
        "component stays below 6 mm, CT annually for 5 years."
    )
    if solid_component_mm is not None and solid_component_mm >= 6:
        rec += (
            " The solid component is 6 mm or larger, which is highly suspicious; "
            "consider PET-CT, biopsy, or resection."
        )
    return rec


def _report_line(
    nodule_type: str,
    multiple: bool,
    risk: str,
    risk_applies: bool,
    size_mm: float,
    solid_component_mm: Optional[float],
    location: Optional[str],
    recommendation: str,
) -> str:
    """Build a paste-ready structured report sentence for the findings block."""
    type_label = NODULE_TYPES[nodule_type]
    loc = (location or "").strip()
    lead = f"{type_label} pulmonary nodule measuring {_fmt_mm(size_mm)}"
    if loc:
        lead += f" in the {loc}"
    if nodule_type == "part_solid" and solid_component_mm is not None:
        lead += f" (solid component {_fmt_mm(solid_component_mm)})"

    multiplicity = "multiple" if multiple else "single"
    if risk_applies:
        context = f"{multiplicity}, {RISK_LABELS[risk]}"
    else:
        context = f"{multiplicity} subsolid"
    return f"{lead}. Fleischner 2017 ({context}): {recommendation}"


def assess(
    nodule_type: str,
    size_mm: float,
    multiple: bool = False,
    risk: str = "low",
    solid_component_mm: Optional[float] = None,
    location: Optional[str] = None,
) -> dict:
    """Return the Fleischner 2017 follow-up recommendation for one nodule.

    `nodule_type` is one of solid, ground_glass, part_solid. `size_mm` is the
    mean of the long- and short-axis diameters. `risk` (low/high) only changes
    the recommendation for solid nodules; the subsolid table is risk-agnostic.
    `solid_component_mm` refines a single part-solid nodule of 6 mm or larger.
    Raises ValueError on an unknown option or a non-positive size.
    """
    if nodule_type not in NODULE_TYPES:
        valid = ", ".join(sorted(NODULE_TYPES))
        raise ValueError(f"Unknown nodule_type {nodule_type!r}. Expected one of: {valid}")
    if risk not in RISK_LABELS:
        valid = ", ".join(sorted(RISK_LABELS))
        raise ValueError(f"Unknown risk {risk!r}. Expected one of: {valid}")

    size_mm = _validate_size(size_mm)
    if solid_component_mm is not None:
        try:
            solid_component_mm = float(solid_component_mm)
        except (TypeError, ValueError):
            raise ValueError("solid_component_mm must be a number")
        if solid_component_mm <= 0:
            solid_component_mm = None

    is_solid = nodule_type == "solid"
    risk_applies = is_solid

    if is_solid:
        band = _solid_band(size_mm)
        size_band, volume_equivalent = _SOLID_BAND_META[band]
        recommendation = _solid_recommendation(multiple, band, risk)
    else:
        band = _subsolid_band(size_mm)
        size_band = _SUBSOLID_BAND_META[band]
        volume_equivalent = None
        recommendation = _subsolid_recommendation(
            nodule_type, multiple, band, solid_component_mm
        )

    report_line = _report_line(
        nodule_type,
        multiple,
        risk,
        risk_applies,
        size_mm,
        solid_component_mm if nodule_type == "part_solid" else None,
        location,
        recommendation,
    )

    return {
        "nodule_type": nodule_type,
        "nodule_type_label": NODULE_TYPES[nodule_type],
        "multiplicity": "multiple" if multiple else "single",
        "risk": risk,
        "risk_applies": risk_applies,
        "size_mm": size_mm,
        "size_band": size_band,
        "volume_equivalent": volume_equivalent,
        "solid_component_mm": solid_component_mm if nodule_type == "part_solid" else None,
        "recommendation": recommendation,
        "report_line": report_line,
        "applicability": _APPLICABILITY,
    }
