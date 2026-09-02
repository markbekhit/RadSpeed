"""Adrenal CT washout characterisation for an incidental adrenal nodule.

Pure, deterministic arithmetic for the public calculator. No patient data is
stored or sent to any model; the tool works on the attenuation values only.
This module is the single source of truth for the rules — the web API and
tests both call it.

The two published metrics are computed from region-of-interest attenuation on a
dedicated adrenal protocol (unenhanced, portal-venous, and 15-minute delayed
phases):

    Absolute percentage washout (APW) = (E - D) / (E - U) x 100
    Relative percentage washout (RPW) = (E - D) / E x 100

where U = unenhanced HU, E = enhanced (portal-venous) HU, D = delayed HU.

Thresholds (reproduced here as a boundary, not clinical advice): an unenhanced
attenuation of 10 HU or less is diagnostic of a lipid-rich adenoma and washout
is not required; otherwise APW of 60% or more (or, when no unenhanced phase is
available, RPW of 40% or more) is consistent with a benign lipid-poor adenoma.

Sources: Caoili EM, Korobkin M, Francis IR, et al. "Adrenal masses:
characterization with combined unenhanced and delayed enhanced CT." Radiology
2002;222(3):629-633. Boland GW, Blake MA, Hahn PF, Mayo-Smith WW. "Incidental
adrenal lesions: principles, techniques, and algorithms for imaging
characterization." Radiology 2008;249(3):756-775.
"""

from __future__ import annotations

from typing import Optional

# Published decision thresholds.
APW_THRESHOLD = 60.0  # % — absolute washout consistent with an adenoma
RPW_THRESHOLD = 40.0  # % — relative washout consistent with an adenoma
LIPID_RICH_HU = 10.0  # unenhanced HU at or below this is a lipid-rich adenoma
MACRO_FAT_HU = -20.0  # unenhanced HU below this suggests macroscopic fat

_APPLICABILITY = (
    "Applies to a homogeneous, non-calcified adrenal nodule without macroscopic "
    "fat, imaged with a dedicated adrenal protocol (unenhanced, portal-venous "
    "at 60-75 s, and 15-minute delayed phases). Some non-adenomas — including "
    "pheochromocytoma and occasional metastases — can also show washout, so "
    "read the numbers with the morphology and the clinical context."
)


def _num(value, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")


def _fmt_hu(value: float) -> str:
    return f"{value:g} HU"


def _fmt_pct(value: float) -> str:
    return f"{value:g}%"


def _round1(value: float) -> float:
    return round(value, 1)


def _report_line(
    unenhanced_hu: Optional[float],
    enhanced_hu: float,
    delayed_hu: float,
    apw: Optional[float],
    rpw: Optional[float],
    category_label: str,
    size_mm: Optional[float],
    location: Optional[str],
    lipid_rich: bool,
) -> str:
    """Build a paste-ready structured report sentence for the findings block."""
    loc = (location or "").strip()
    lead = f"{loc} adrenal nodule" if loc else "Adrenal nodule"
    if size_mm is not None:
        lead += f" measuring {size_mm:g} mm"

    if lipid_rich and unenhanced_hu is not None:
        return (
            f"{lead} with unenhanced attenuation {_fmt_hu(unenhanced_hu)} — "
            f"{category_label}."
        )

    phases = []
    if unenhanced_hu is not None:
        phases.append(f"unenhanced {_fmt_hu(unenhanced_hu)}")
    phases.append(f"portal venous {_fmt_hu(enhanced_hu)}")
    phases.append(f"15-minute delayed {_fmt_hu(delayed_hu)}")
    attenuations = ", ".join(phases)

    metrics = []
    if apw is not None:
        metrics.append(f"absolute washout {_fmt_pct(apw)}")
    if rpw is not None:
        metrics.append(f"relative washout {_fmt_pct(rpw)}")
    metric_text = ", ".join(metrics) if metrics else "washout not calculable"

    return f"{lead}: {attenuations}. {metric_text} — {category_label}."


def assess(
    enhanced_hu: float,
    delayed_hu: float,
    unenhanced_hu: Optional[float] = None,
    size_mm: Optional[float] = None,
    location: Optional[str] = None,
) -> dict:
    """Characterise an adrenal nodule from its CT attenuation values.

    `enhanced_hu` (portal-venous phase) and `delayed_hu` (15-minute delayed
    phase) are required. `unenhanced_hu` is optional; when supplied it enables
    the absolute washout and the lipid-rich adenoma shortcut, otherwise only the
    relative washout is reported. Raises ValueError on a non-numeric value or
    when neither washout can be calculated.
    """
    enhanced_hu = _num(enhanced_hu, "enhanced_hu")
    delayed_hu = _num(delayed_hu, "delayed_hu")
    if unenhanced_hu is not None and unenhanced_hu != "":
        unenhanced_hu = _num(unenhanced_hu, "unenhanced_hu")
    else:
        unenhanced_hu = None

    if size_mm is not None:
        size_mm = _num(size_mm, "size_mm")
        if size_mm <= 0:
            size_mm = None

    # Absolute washout needs an unenhanced phase and genuine enhancement between
    # the unenhanced and portal-venous phases; otherwise the ratio is undefined.
    apw: Optional[float] = None
    enhancement = None
    if unenhanced_hu is not None:
        enhancement = enhanced_hu - unenhanced_hu
        if enhancement > 0:
            apw = _round1((enhanced_hu - delayed_hu) / enhancement * 100.0)

    # Relative washout needs only the enhanced and delayed phases.
    rpw: Optional[float] = None
    if enhanced_hu > 0:
        rpw = _round1((enhanced_hu - delayed_hu) / enhanced_hu * 100.0)

    if apw is None and rpw is None:
        raise ValueError(
            "Cannot calculate washout: the enhanced (portal-venous) attenuation "
            "must be greater than 0 and, for absolute washout, greater than the "
            "unenhanced attenuation."
        )

    lipid_rich = unenhanced_hu is not None and unenhanced_hu <= LIPID_RICH_HU
    macro_fat = unenhanced_hu is not None and unenhanced_hu < MACRO_FAT_HU

    apw_meets = apw is not None and apw >= APW_THRESHOLD
    rpw_meets = rpw is not None and rpw >= RPW_THRESHOLD

    # When an unenhanced phase is available the absolute washout is the primary
    # criterion; without it, fall back to the relative washout.
    primary_metric = "APW" if apw is not None else "RPW"
    washout_positive = apw_meets if apw is not None else rpw_meets

    if lipid_rich:
        category = "lipid_rich_adenoma"
        category_label = (
            "diagnostic of a benign lipid-rich adenoma; washout analysis not required"
        )
        recommendation = (
            "Unenhanced attenuation of 10 HU or less is diagnostic of a benign "
            "lipid-rich adenoma. No adrenal follow-up is required."
        )
    elif washout_positive:
        category = "lipid_poor_adenoma"
        metric_name = "Absolute" if primary_metric == "APW" else "Relative"
        category_label = "meets washout criteria for a benign lipid-poor adenoma"
        recommendation = (
            f"{metric_name} washout meets the criterion for a benign lipid-poor "
            "adenoma. No further adrenal imaging is usually required."
        )
    else:
        category = "indeterminate"
        category_label = "does not meet adenoma washout criteria; indeterminate"
        recommendation = (
            "The washout does not meet adenoma criteria, so the nodule is "
            "indeterminate. Correlate with any prior imaging for stability and, "
            "in the appropriate clinical context (for example a known primary "
            "malignancy), consider chemical-shift MRI, biopsy, or PET-CT."
        )

    if macro_fat:
        recommendation += (
            " The unenhanced attenuation is markedly low, which suggests "
            "macroscopic fat (for example a myelolipoma)."
        )

    report_line = _report_line(
        unenhanced_hu,
        enhanced_hu,
        delayed_hu,
        apw,
        rpw,
        category_label,
        size_mm,
        location,
        lipid_rich,
    )

    return {
        "unenhanced_hu": unenhanced_hu,
        "enhanced_hu": enhanced_hu,
        "delayed_hu": delayed_hu,
        "size_mm": size_mm,
        "apw": apw,
        "rpw": rpw,
        "apw_threshold": APW_THRESHOLD,
        "rpw_threshold": RPW_THRESHOLD,
        "apw_meets": apw_meets,
        "rpw_meets": rpw_meets,
        "primary_metric": primary_metric,
        "washout_positive": bool(washout_positive),
        "lipid_rich_adenoma": bool(lipid_rich),
        "macroscopic_fat": bool(macro_fat),
        "category": category,
        "category_label": category_label,
        "recommendation": recommendation,
        "report_line": report_line,
        "applicability": _APPLICABILITY,
    }
