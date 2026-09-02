// RadSpeed adrenal CT washout calculator — public free tool.
// Posts the attenuation values to /api/adrenal/washout and renders the
// absolute and relative washout, the adenoma category and a paste-ready report
// line. Deterministic; no patient data is stored.

(() => {
  const $ = (id) => document.getElementById(id);

  function setStatus(msg, kind) {
    const el = $("status");
    el.textContent = msg || "";
    el.style.color = kind === "error" ? "var(--red)" : "var(--muted)";
  }

  const CATEGORY_LABELS = {
    lipid_rich_adenoma: "Lipid-rich adenoma",
    lipid_poor_adenoma: "Lipid-poor adenoma",
    indeterminate: "Indeterminate nodule",
  };

  function fmtPct(value) {
    return value === null || value === undefined ? "—" : value + "%";
  }

  function setMetric(metricId, valId, noteId, value, meets, threshold, active) {
    $(valId).textContent = fmtPct(value);
    const note = $(noteId);
    const box = $(metricId);
    box.classList.toggle("pass", !!meets && active);
    if (value === null || value === undefined) {
      note.textContent = "threshold " + threshold;
      return;
    }
    if (!active) {
      note.textContent = "threshold " + threshold;
    } else {
      note.textContent = (meets ? "meets " : "below ") + threshold;
    }
  }

  function render(r) {
    $("category").textContent = CATEGORY_LABELS[r.category] || r.category;

    const bits = [];
    if (r.size_mm) bits.push(r.size_mm + " mm");
    bits.push(r.washout_positive || r.lipid_rich_adenoma ? "benign features" : "does not meet adenoma criteria");
    $("summary").textContent = bits.join(" · ");

    // Absolute washout is the primary metric when an unenhanced phase is given.
    const apwActive = r.apw !== null && r.apw !== undefined && !r.lipid_rich_adenoma;
    const rpwActive =
      !r.lipid_rich_adenoma && r.primary_metric === "RPW";
    setMetric("apw-metric", "apw-val", "apw-note", r.apw, r.apw_meets, "≥60%", apwActive);
    setMetric("rpw-metric", "rpw-val", "rpw-note", r.rpw, r.rpw_meets, "≥40%", rpwActive);

    $("recommendation").textContent = r.recommendation;
    $("report-line").textContent = r.report_line;
  }

  function clear(msg) {
    $("category").textContent = "—";
    $("summary").textContent = msg || "";
    $("apw-val").textContent = "—";
    $("rpw-val").textContent = "—";
    $("apw-metric").classList.remove("pass");
    $("rpw-metric").classList.remove("pass");
    $("apw-note").textContent = "threshold ≥60%";
    $("rpw-note").textContent = "threshold ≥40%";
    $("recommendation").textContent = "";
    $("report-line").textContent = "";
  }

  function numOrNull(id) {
    const raw = $(id).value.trim();
    if (raw === "") return null;
    const v = parseFloat(raw);
    return Number.isNaN(v) ? null : v;
  }

  async function recommend() {
    const enhanced = numOrNull("enhanced_hu");
    const delayed = numOrNull("delayed_hu");
    if (enhanced === null || delayed === null) {
      clear("Enter the portal-venous and delayed attenuation to see the washout.");
      setStatus("");
      return;
    }
    const payload = {
      enhanced_hu: enhanced,
      delayed_hu: delayed,
      unenhanced_hu: numOrNull("unenhanced_hu"),
      size_mm: numOrNull("size_mm"),
      location: $("location").value.trim() || null,
    };
    try {
      const resp = await fetch("/api/adrenal/washout", {
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
        clear("");
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
    const inputs = ["unenhanced_hu", "enhanced_hu", "delayed_hu", "size_mm", "location"].map($);
    for (const el of inputs) {
      el.addEventListener("change", recommend);
      el.addEventListener("input", recommend);
    }
    $("btn-copy").addEventListener("click", copyReport);
    recommend(); // initial render for the default values
  });
})();
