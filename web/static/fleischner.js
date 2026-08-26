// RadSpeed Fleischner 2017 pulmonary nodule calculator — public free tool.
// Posts the nodule descriptors to /api/fleischner/recommend and renders the
// follow-up recommendation and a paste-ready report line. Deterministic; no
// patient data is stored.

(() => {
  const $ = (id) => document.getElementById(id);

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
  }

  async function recommend() {
    syncFields();
    const type = $("nodule_type").value;
    const payload = {
      nodule_type: type,
      size_mm: $("size_mm").value ? parseFloat($("size_mm").value) : 0,
      multiple: $("multiple").checked,
      risk: $("risk").value,
      solid_component_mm:
        type === "part_solid" && $("solid_component_mm").value
          ? parseFloat($("solid_component_mm").value)
          : null,
      location: $("location").value.trim() || null,
    };
    if (!payload.size_mm || payload.size_mm <= 0) {
      $("recommendation").textContent = "";
      $("report-line").textContent = "";
      $("size-band").textContent = "—";
      $("nodule-summary").textContent = "Enter the mean nodule diameter to see the recommendation.";
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
    const inputs = ["nodule_type", "size_mm", "risk", "solid_component_mm", "location"].map($);
    for (const el of inputs) {
      el.addEventListener("change", recommend);
      if (el.tagName === "INPUT") el.addEventListener("input", recommend);
    }
    $("multiple").addEventListener("change", recommend);
    $("btn-copy").addEventListener("click", copyReport);
    recommend(); // initial render for the default selection
  });
})();
