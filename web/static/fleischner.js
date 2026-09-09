// RadSpeed Fleischner 2017 pulmonary nodule calculator — public free tool.
// Posts the nodule descriptors to /api/fleischner/recommend and renders the
// follow-up recommendation, the interval change against the prior study and a
// paste-ready report line. Deterministic; no patient data is stored.
//
// The measurement rule (mean of the two axes, rounded to the nearest whole
// millimetre) and the growth thresholds live in web/fleischner.py. This file
// only collects the inputs and renders what the server returns, so the browser
// never holds a second copy of the guideline.

(() => {
  const $ = (id) => document.getElementById(id);
  const num = (id) => {
    const raw = $(id).value.trim();
    if (!raw) return null;
    const value = parseFloat(raw);
    return Number.isNaN(value) || value <= 0 ? null : value;
  };

  function setStatus(msg, kind) {
    const el = $("status");
    el.textContent = msg || "";
    el.style.color = kind === "error" ? "var(--red)" : "var(--muted)";
  }

  // Risk only changes the recommendation for solid nodules; the part-solid
  // field only matters for a single part-solid nodule of 6 mm or larger.
  function syncFields() {
    const type = $("nodule_type").value;
    const isSolid = type === "solid";
    const isPartSolid = type === "part_solid";
    const size = parseFloat($("size_mm").value);

    $("risk-field").style.display = isSolid ? "" : "none";
    $("risk-note").style.display = isSolid ? "none" : "";

    // Both axes entered means the server owns the mean, so lock the field to
    // stop the two entry routes disagreeing.
    const axesGiven = num("long_axis_mm") !== null && num("short_axis_mm") !== null;
    $("size_mm").readOnly = axesGiven;
    $("size_mm").style.opacity = axesGiven ? "0.7" : "";

    const showSolidComponent =
      isPartSolid && !$("multiple").checked && !Number.isNaN(size) && size >= 6;
    $("solid-component-field").style.display = showSolidComponent ? "" : "none";
  }

  function render(r) {
    $("size-band").textContent = r.size_band;
    $("nodule-summary").textContent =
      r.nodule_type_label +
      " nodule · " +
      r.multiplicity +
      (r.risk_applies ? " · " + r.risk + "-risk" : "") +
      (r.volume_equivalent ? " · " + r.volume_equivalent : "");
    $("recommendation").textContent = r.recommendation;
    $("report-line").textContent = r.report_line;

    if (r.measurement) {
      $("size_mm").value = r.measurement.mean_diameter_mm;
      $("measurement-note").textContent = r.measurement.measurement_note;
    } else {
      $("measurement-note").textContent = "";
    }

    const box = $("interval-change");
    if (r.comparison) {
      const tags = { growth: "Growth", smaller: "Smaller", stable: "Stable" };
      box.style.display = "";
      box.dataset.status = r.comparison.status;
      $("change-tag").textContent = tags[r.comparison.status] || "Interval change";
      $("change-summary").textContent = r.comparison.summary;
      $("change-note").textContent = r.comparison.growth_note || "";
    } else {
      box.style.display = "none";
      box.removeAttribute("data-status");
    }
  }

  async function recommend() {
    syncFields();
    const type = $("nodule_type").value;
    const longAxis = num("long_axis_mm");
    const shortAxis = num("short_axis_mm");
    const axesGiven = longAxis !== null && shortAxis !== null;
    const payload = {
      nodule_type: type,
      size_mm: axesGiven ? null : num("size_mm") || 0,
      multiple: $("multiple").checked,
      risk: $("risk").value,
      solid_component_mm:
        type === "part_solid" && $("solid_component_mm").value
          ? parseFloat($("solid_component_mm").value)
          : null,
      location: $("location").value.trim() || null,
      long_axis_mm: axesGiven ? longAxis : null,
      short_axis_mm: axesGiven ? shortAxis : null,
      prior_size_mm: num("prior_size_mm"),
      interval_months: num("interval_months"),
      volume_mm3: num("volume_mm3"),
      prior_volume_mm3: num("prior_volume_mm3"),
    };
    // Volume comparison needs both studies; one alone tells us nothing.
    if (payload.volume_mm3 === null || payload.prior_volume_mm3 === null) {
      payload.volume_mm3 = null;
      payload.prior_volume_mm3 = null;
    }
    if (!axesGiven && (!payload.size_mm || payload.size_mm <= 0)) {
      $("recommendation").textContent = "";
      $("report-line").textContent = "";
      $("size-band").textContent = "—";
      $("measurement-note").textContent = "";
      $("interval-change").style.display = "none";
      $("nodule-summary").textContent =
        "Enter both axes, or the mean nodule diameter, to see the recommendation.";
      setStatus("");
      return;
    }
    try {
      const resp = await fetch("/api/fleischner/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        let detail = resp.status + " " + resp.statusText;
        try {
          const j = await resp.json();
          if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch (_) {}
        throw new Error(detail);
      }
      render(await resp.json());
      setStatus("");
    } catch (err) {
      setStatus("Error: " + (err.message || err), "error");
    }
  }

  async function copyReport() {
    const text = ($("report-line").textContent || "").trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Report line copied to clipboard.");
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) {}
      document.body.removeChild(ta);
      setStatus(ok ? "Report line copied to clipboard." : "Copy failed — select and copy manually.", ok ? "" : "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const inputs = [
      "nodule_type",
      "long_axis_mm",
      "short_axis_mm",
      "size_mm",
      "risk",
      "solid_component_mm",
      "location",
      "prior_size_mm",
      "interval_months",
      "volume_mm3",
      "prior_volume_mm3",
    ].map($);
    for (const el of inputs) {
      el.addEventListener("change", recommend);
      if (el.tagName === "INPUT") el.addEventListener("input", recommend);
    }
    $("multiple").addEventListener("change", recommend);
    $("btn-copy").addEventListener("click", copyReport);
    recommend(); // initial render for the default selection
  });
})();
