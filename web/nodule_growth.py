"""Pulmonary nodule growth and volume doubling time between two CT studies.

Pure, deterministic arithmetic for the public calculator. No patient data is
stored or sent to any model; the tool works on the measurements and the scan
interval only. This module is the single source of truth for the rules — the
web API and tests both call it.

Volume doubling time (VDT) uses the modified Schwartz exponential growth model:

    VDT = t x ln 2 / ln(V2 / V1)

where t is the interval in days and V1, V2 are the prior and current volumes.
When only mean diameters are available the volume is approximated as a sphere
(V = pi/6 x d^3), so VDT = t x ln 2 / (3 x ln(D2 / D1)). Diameter-based VDT
cubes any measurement error and is much less reliable than volumetry.

Two published frameworks read the result (reproduced here as boundaries, not
clinical advice):

* Australian National Lung Cancer Screening Program (NLCSP) Nodule Management
  Protocol, explanatory note 6 — volumetry: growing is an increase of more
  than 25% with VDT under 600 days; an increase of more than 25% with VDT over
  600 days is slow growth only when it persists across more than one scan
  interval, otherwise stable; a change within +/-25% is stable; a decrease of
  25% or more is decreased. Mean diameter: an increase of more than 1.5 mm is
  growing over 24 months or less and slowly growing over more than 24 months;
  a change within +/-1.5 mm is stable; a decrease of 1.5 mm or more is
  decreased.
* British Thoracic Society 2015 pulmonary nodule guideline (volumetry): a
  volume increase of 25% or more is significant growth; VDT under 400 days
  supports further investigation, 400-600 days supports yearly surveillance or
  biopsy by preference, and over 600 days supports discharge or ongoing
  surveillance.

Sources: Australian Government Department of Health, Disability and Ageing.
NLCSP Nodule Management Protocol (2025). Callister MEJ, Baldwin DR, Akram AR,
et al. British Thoracic Society guidelines for the investigation and management
of pulmonary nodules. Thorax 2015;70(Suppl 2):ii1-ii54.
"""

from __future__ import annotations

import math
from typing import Optional

VOLUME_CHANGE_PERCENT = 25.0  # % volume change inside measurement error
NLCSP_VDT_DAYS = 600.0  # NLCSP growing versus slow-growth boundary
BTS_FAST_VDT_DAYS = 400.0  # BTS: below this, offer further investigation
BTS_SLOW_VDT_DAYS = 600.0  # BTS: above this, consider discharge
DIAMETER_CHANGE_MM = 1.5  # NLCSP mean-diameter change inside measurement error
SLOW_GROWTH_MONTHS = 24.0  # NLCSP: diameter growth over more than this is slow
DAYS_PER_MONTH = 365.25 / 12
MAX_VOLUME_MM3 = 1_000_000.0  # larger than any lung nodule; blocks overflow
MAX_DIAMETER_MM = 300.0

_APPLICABILITY = (
    "Use the same measurement method, reconstruction and, ideally, the same "
    "volumetry software on both studies. Compare with the earliest available CT "
    "so slow growth is not missed. For a part-solid nodule, track the solid "
    "component. Volume doubling time is one input to nodule management, not a "
    "diagnosis."
)


def _num(value, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a number")
    return result


def _positive(value, field: str) -> float:
    result = _num(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be greater than 0")
    return result


def _fmt(value: float) -> str:
    return f"{value:g}"


def _whole(value: float) -> str:
    return str(round(value)) if value >= 1 else _fmt(value)


def _sphere_volume(diameter_mm: float) -> float:
    return math.pi / 6 * diameter_mm ** 3


# The readings compare the same rounded values the page displays, so a shown
# "600 days" never sits beside "VDT under 600 days" and one-decimal diameters
# never drift across the 1.5 mm boundary through floating-point subtraction.
def _nlcsp_volume(change_percent: float, vdt_days: Optional[int]) -> tuple[str, str]:
    if change_percent <= -VOLUME_CHANGE_PERCENT:
        return "decreased", "Decreased: volume fell by 25% or more."
    if change_percent <= VOLUME_CHANGE_PERCENT:
        return "stable", "Stable: volume change within ±25%, inside measurement error."
    if vdt_days is not None and vdt_days < NLCSP_VDT_DAYS:
        return "growing", "Growing: volume increase over 25% with VDT under 600 days."
    return (
        "slow_growth_pattern",
        "Stable on this single interval: volume increase over 25% with VDT of 600 "
        "days or more. The NLCSP calls this slowly growing only when the pattern "
        "holds across more than one scan interval.",
    )


def _nlcsp_diameter(change_mm: float, interval_months: float) -> tuple[str, str]:
    if change_mm <= -DIAMETER_CHANGE_MM:
        return "decreased", "Decreased: mean diameter fell by 1.5 mm or more."
    if change_mm <= DIAMETER_CHANGE_MM:
        return "stable", "Stable: mean diameter change within ±1.5 mm."
    if interval_months <= SLOW_GROWTH_MONTHS:
        return "growing", "Growing: mean diameter increase over 1.5 mm within 24 months."
    return "slowly_growing", "Slowly growing: mean diameter increase over 1.5 mm over more than 24 months."


def _bts(change_percent: float, vdt_days: Optional[int]) -> tuple[str, str]:
    if change_percent <= -VOLUME_CHANGE_PERCENT:
        return (
            "decreased",
            "Volume fell by 25% or more. The BTS doubling-time thresholds do not apply.",
        )
    if change_percent < VOLUME_CHANGE_PERCENT or vdt_days is None:
        return "stable", "Stable: volume change under 25%."
    if vdt_days < BTS_FAST_VDT_DAYS:
        return (
            "fast",
            "VDT under 400 days: BTS advises offering further investigation "
            "(biopsy, imaging or resection).",
        )
    if vdt_days <= BTS_SLOW_VDT_DAYS:
        return (
            "intermediate",
            "VDT 400–600 days: BTS advises yearly surveillance or biopsy, by "
            "patient preference.",
        )
    return (
        "slow",
        "VDT over 600 days: BTS advises considering discharge or ongoing CT "
        "surveillance, taking account of patient preference, fitness and age.",
    )


def assess(
    prior: float,
    current: float,
    interval_days: float,
    method: str = "volume",
) -> dict:
    """Compare a nodule across two studies and return the growth metrics.

    `method` is "volume" (prior and current in mm3, the preferred method) or
    "diameter" (prior and current mean diameter in mm). `interval_days` is the
    time between the two studies. Raises ValueError on a missing, non-numeric,
    zero or negative value, or an unknown method.
    """
    if method not in ("volume", "diameter"):
        raise ValueError("method must be 'volume' or 'diameter'")
    prior = _positive(prior, "prior")
    current = _positive(current, "current")
    limit = MAX_VOLUME_MM3 if method == "volume" else MAX_DIAMETER_MM
    if prior > limit or current > limit:
        unit_name = "mm³" if method == "volume" else "mm"
        raise ValueError(f"measurements must be {limit:g} {unit_name} or less")
    interval_days = _positive(interval_days, "interval_days")
    if interval_days < 1:
        raise ValueError("interval_days must be at least 1 day")
    if interval_days > 36500:
        raise ValueError("interval_days must be 100 years or less")

    if method == "volume":
        prior_volume, current_volume = prior, current
        unit = "mm³"
    else:
        prior_volume, current_volume = _sphere_volume(prior), _sphere_volume(current)
        unit = "mm"

    ratio = current_volume / prior_volume
    volume_change_percent = (ratio - 1) * 100
    vdt_days: Optional[float] = None
    if ratio > 1:
        vdt_days = interval_days * math.log(2) / math.log(ratio)

    change_rounded = round(volume_change_percent, 1) + 0.0  # no "-0%"
    vdt_rounded = round(vdt_days) if vdt_days is not None else None

    # Rounded like the page shows it, so two calendar years across 29 February
    # (731 days, "24.0 months") still count as 24 months or less.
    interval_months = round(interval_days / DAYS_PER_MONTH, 1)
    diameter_change_mm: Optional[float] = None
    if method == "volume":
        nlcsp_status, nlcsp_text = _nlcsp_volume(change_rounded, vdt_rounded)
        bts_band, bts_text = _bts(change_rounded, vdt_rounded)
    else:
        diameter_change_mm = round(current - prior, 1)
        nlcsp_status, nlcsp_text = _nlcsp_diameter(diameter_change_mm, interval_months)
        bts_band = None
        bts_text = (
            "BTS 2015 bases growth on volumetry. Use CT volumes for the BTS VDT "
            "thresholds where the software allows."
        )

    # The page adds any location in the browser, so free text never reaches
    # the server.
    lead = "Pulmonary nodule"
    if method == "volume":
        # NLCSP note 5a: report volumes to the nearest whole mm³.
        size_text = f"volume {_whole(current)} mm³, previously {_whole(prior)} mm³"
    else:
        # NLCSP note 5b: report mean diameter to one decimal place.
        size_text = f"mean diameter {current:.1f} mm, previously {prior:.1f} mm"
    shown_days = round(interval_days, 1)
    interval_text = f"{_fmt(shown_days)} day{'' if shown_days == 1 else 's'}"
    # A doubling time is only a growth rate when the change exceeds
    # measurement error; otherwise the report line must not state one.
    within_error = nlcsp_status == "stable"
    if method == "diameter":
        # The diameter rule decides growth here, so the line reports the
        # measured diameter change; the sphere-based VDT is only an estimate.
        growth_text = f"mean diameter change {diameter_change_mm:+.1f} mm"
        if within_error:
            growth_text += ", within measurement error"
        elif vdt_rounded is not None and nlcsp_status != "decreased":
            growth_text += (
                f", estimated volume doubling time {vdt_rounded} days "
                "(from mean diameter)"
            )
    elif vdt_rounded is not None and within_error:
        growth_text = (
            f"volume change {change_rounded:+g}%, within measurement error "
            "(no reliable doubling time)"
        )
    elif vdt_rounded is not None:
        growth_text = (
            f"volume change {change_rounded:+g}%, volume doubling time "
            f"{vdt_rounded} days"
        )
    else:
        growth_text = f"volume change {change_rounded:+g}%, no volume increase"
    report_line = f"{lead}: {size_text} ({interval_text} earlier); {growth_text}."

    warnings = []
    if method == "diameter":
        warnings.append(
            "Diameter-based VDT assumes a sphere and cubes any measurement error. "
            "Use volumetry where possible."
        )
    if interval_days < 28:
        warnings.append(
            "The interval is under four weeks. Short intervals make VDT unstable "
            "because small measurement differences dominate."
        )
    if within_error and vdt_rounded is not None:
        if method == "diameter":
            warnings.append(
                "The mean-diameter change is within ±1.5 mm measurement error, so "
                "the VDT is not a reliable growth rate."
            )
        elif change_rounded == VOLUME_CHANGE_PERCENT:
            warnings.append(
                "A change of exactly 25% is stable under the NLCSP (which needs "
                "more than 25%) but significant under BTS (25% or more)."
            )
        else:
            warnings.append(
                "The volume change is within ±25% measurement error, so the VDT is "
                "not a reliable growth rate."
            )

    return {
        "method": method,
        "prior": prior,
        "current": current,
        "unit": unit,
        "interval_days": round(interval_days, 1),
        "interval_months": interval_months,
        "prior_volume_mm3": round(prior_volume, 1),
        "current_volume_mm3": round(current_volume, 1),
        "volume_change_percent": change_rounded,
        "diameter_change_mm": diameter_change_mm,
        "vdt_days": vdt_rounded,
        "nlcsp_status": nlcsp_status,
        "nlcsp_text": nlcsp_text,
        "bts_band": bts_band,
        "bts_text": bts_text,
        "warnings": warnings,
        "report_line": report_line,
        "applicability": _APPLICABILITY,
    }
