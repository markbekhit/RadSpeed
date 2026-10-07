// RadSpeed lung nodule volume doubling time calculator — public free tool.
// Posts two measurements and the interval to /api/nodule-growth/vdt and renders
// the volume change, the doubling time, the NLCSP and BTS readings and a
// paste-ready report line. Scan dates and the location stay in the browser; only
// the numbers are sent. Deterministic; no patient data is stored.

(() => {
  const $ = (id) => document.getElementById(id);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const REPORT_LEAD = "Pulmonary nodule";
  let requestSeq = 0;
  let lastLine = "";

  function setStatus(msg, kind) {
    const el = $("status");
    el.textContent = msg || "";
    el.style.color = kind === "error" ? "var(--red)" : "var(--muted)";
  }

  const NLCSP_HEADLINES = {
    growing: "Growing",
    slow_growth_pattern: "Stable or slowly growing",
    slowly_growing: "Slowly growing",
    stable: "Stable",
    decreased: "Decreased",
  };

  const METHOD_EXAMPLES = { volume: ["120", "180"], diameter: ["6.0", "7.6"] };

  function numOrNull(id) {
    const raw = $(id).value.trim();
    if (raw === "") return null;
    const v = parseFloat(raw);
    return Number.isNaN(v) ? null : v;
  }

  function syncLabels() {
    const volume = $("method").value === "volume";
    const unit = volume ? "volume (mm³)" : "mean diameter (mm)";
    $("prior-label").textContent = "Prior " + unit;
    $("current-label").textContent = "Current " + unit;
  }

  // When both scan dates are set, they define the interval.
  function syncIntervalFromDates() {
    const a = $("prior_date").value;
    const b = $("current_date").value;
    if (!a || !b) return;
    const days = Math.round((Date.parse(b) - Date.parse(a)) / DAY_MS);
    if (Number.isFinite(days)) $("interval_days").value = String(days);
  }

  function render(r) {
    $("headline").textContent = NLCSP_HEADLINES[r.nlcsp_status] || r.nlcsp_status;
    const bits = [r.interval_days + " days (" + r.interval_months + " months)"];
    if (r.method === "diameter") {
      bits.push("diameter change " + (r.diameter_change_mm > 0 ? "+" : "") + r.diameter_change_mm + " mm");
      bits.push("volumes estimated as spheres");
    } else {
      bits.push(r.prior_volume_mm3 + " → " + r.current_volume_mm3 + " mm³");
    }
    $("summary").textContent = bits.join(" · ");

    const change = r.volume_change_percent;
    $("change-val").textContent = (change > 0 ? "+" : "") + change + "%";
    $("vdt-val").textContent = r.vdt_days === null ? "—" : String(r.vdt_days);
    $("vdt-note").textContent = r.vdt_days === null ? "no volume increase" : "days";
    $("change-note").textContent =
      r.method === "diameter" ? "from mean diameter; ±1.5 mm rule applies" : "±25% is measurement error";

    $("nlcsp-text").textContent = r.nlcsp_text;
    $("bts-text").textContent = r.bts_text;

    const list = $("warnings");
    list.textContent = "";
    for (const w of r.warnings || []) {
      const li = document.createElement("li");
      li.textContent = w;
      list.appendChild(li);
    }
    lastLine = r.report_line;
    $("report-line").textContent = withLocation(lastLine);
  }

  // The location is added here so free text never leaves the browser.
  function withLocation(line) {
    const loc = $("location").value.trim().slice(0, 80);
    if (!loc || !line.startsWith(REPORT_LEAD)) return line;
    const lead = loc.charAt(0).toUpperCase() + loc.slice(1) + " pulmonary nodule";
    return lead + line.slice(REPORT_LEAD.length);
  }

  function clear(msg) {
    $("headline").textContent = "—";
    $("summary").textContent = msg || "";
    $("change-val").textContent = "—";
    $("vdt-val").textContent = "—";
    $("vdt-note").textContent = "days";
    $("nlcsp-text").textContent = "";
    $("bts-text").textContent = "";
    $("warnings").textContent = "";
    $("report-line").textContent = "";
    lastLine = "";
  }

  async function calculate() {
    const seq = ++requestSeq;
    const prior = numOrNull("prior");
    const current = numOrNull("current");
    const interval = numOrNull("interval_days");
    if (prior === null || current === null || interval === null) {
      clear("Enter the prior and current measurement and the interval to see the doubling time.");
      setStatus("");
      return;
    }
    if (prior <= 0 || current <= 0 || interval < 1) {
      clear("");
      setStatus(
        interval < 1
          ? "Error: enter an interval of at least 1 day, with the current scan after the prior scan."
          : "Error: measurements must be greater than 0.",
        "error"
      );
      return;
    }
    const payload = {
      prior: prior,
      current: current,
      interval_days: interval,
      method: $("method").value,
    };
    try {
      const resp = await fetch("/api/nodule-growth/vdt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (seq !== requestSeq) return; // a newer input has already been sent
      if (!resp.ok) {
        let detail = resp.status + " " + resp.statusText;
        try {
          const j = await resp.json();
          if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch (_) {}
        clear("");
        throw new Error(detail);
      }
      const result = await resp.json();
      if (seq !== requestSeq) return;
      render(result);
      setStatus("");
    } catch (err) {
      if (seq !== requestSeq) return;
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
      $("btn-copy").focus({ preventScroll: true });
      if (!ok) {
        const range = document.createRange();
        range.selectNodeContents($("report-line"));
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
      setStatus(ok ? "Report line copied to clipboard." : "Automatic copy is unavailable. The report line is selected. Press Ctrl+C or ⌘C. On a phone, touch and hold the report line, then choose Copy.", ok ? "" : "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Values in one unit mean nothing in the other, so switch to that unit's example.
    $("method").addEventListener("change", () => {
      const example = METHOD_EXAMPLES[$("method").value];
      $("prior").value = example[0];
      $("current").value = example[1];
      syncLabels();
      calculate();
    });
    for (const id of ["prior_date", "current_date"]) {
      $(id).addEventListener("change", () => {
        syncIntervalFromDates();
        calculate();
      });
    }
    // A typed interval replaces the dates so the two never disagree.
    $("interval_days").addEventListener("input", () => {
      $("prior_date").value = "";
      $("current_date").value = "";
    });
    // The location changes only the wording, so it re-renders without a request.
    $("location").addEventListener("input", () => {
      if (lastLine) $("report-line").textContent = withLocation(lastLine);
    });
    for (const id of ["prior", "current", "interval_days"]) {
      $(id).addEventListener("input", calculate);
      $(id).addEventListener("change", calculate);
    }
    $("btn-copy").addEventListener("click", copyReport);
    syncLabels();
    calculate(); // initial render for the default values
  });
})();
