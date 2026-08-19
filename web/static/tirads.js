// RadSpeed ACR TI-RADS calculator — public free tool.
// Posts the selected ultrasound features to /api/tirads/score and renders the
// TR level, thresholds and a paste-ready report line. Deterministic; no patient
// data is stored.

(() => {
  const $ = (id) => document.getElementById(id);

  function collectFoci() {
    return Array.from(document.querySelectorAll(".foci"))
      .filter((el) => el.checked)
      .map((el) => el.value);
  }

  function setStatus(msg, kind) {
    const el = $("status");
    el.textContent = msg || "";
    el.style.color = kind === "error" ? "var(--red)" : "var(--muted)";
  }

  function render(r) {
    const level = r.level; // e.g. "TR4"
    const n = level.replace("TR", "");
    const levelEl = $("level");
    levelEl.textContent = level;
    levelEl.className = "tirads-level tr-" + n;

    $("risk-badge").textContent = "Est. malignancy " + r.malignancy_risk;
    $("points").textContent =
      r.points + " point" + (r.points === 1 ? "" : "s") + " · " + r.level_label;

    if (r.fna_threshold_cm == null) {
      $("thresholds").innerHTML = "<strong>No FNA or follow-up ultrasound</strong> indicated at any size.";
    } else {
      $("thresholds").innerHTML =
        "<strong>FNA</strong> if &ge;" + r.fna_threshold_cm + " cm &middot; " +
        "<strong>Follow-up ultrasound</strong> if &ge;" + r.follow_threshold_cm +
        " cm (" + r.follow_intervals + ").";
    }

    $("management").textContent = r.management;
    $("report-line").textContent = r.report_line;
  }

  async function score() {
    const payload = {
      composition: $("composition").value,
      echogenicity: $("echogenicity").value,
      shape: $("shape").value,
      margin: $("margin").value,
      foci: collectFoci(),
      size_mm: $("size_mm").value ? parseFloat($("size_mm").value) : null,
      location: $("location").value.trim() || null,
    };
    try {
      const resp = await fetch("/api/tirads/score", {
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
      "composition", "echogenicity", "shape", "margin", "size_mm", "location",
    ].map($);
    for (const el of inputs) {
      el.addEventListener("change", score);
      if (el.tagName === "INPUT") el.addEventListener("input", score);
    }
    for (const el of document.querySelectorAll(".foci")) {
      el.addEventListener("change", score);
    }
    $("btn-copy").addEventListener("click", copyReport);
    score(); // initial render for the default selection
  });
})();
