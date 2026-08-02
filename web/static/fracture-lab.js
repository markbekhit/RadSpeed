(() => {
  "use strict";

  const MAX_IMAGES = 4;
  const MAX_BYTES = 12 * 1024 * 1024;
  const supportedTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
  const files = [];

  const byId = (id) => document.getElementById(id);
  const input = byId("fracture-file-input");
  const dropZone = byId("fracture-drop-zone");
  const previewList = byId("fracture-preview-list");
  const chooseButton = byId("fracture-choose");
  const clearButton = byId("fracture-clear");
  const analyseButton = byId("fracture-analyse");
  const contextInput = byId("fracture-context");
  const status = byId("fracture-status");
  const result = byId("fracture-result");

  if (!input || !dropZone || !previewList || !analyseButton || !result) return;

  const create = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const setStatus = (message, isError = false) => {
    status.textContent = message;
    status.classList.toggle("error", isError);
  };

  const resetResult = () => {
    result.hidden = true;
    result.replaceChildren();
  };

  const renderPreviews = () => {
    previewList.replaceChildren();
    files.forEach((item, index) => {
      const card = create("div", "fracture-preview");
      const image = create("img");
      image.src = item.url;
      image.alt = `Selected X-ray view ${index + 1}`;
      const footer = create(
        "div",
        "fracture-preview-footer",
        `View ${index + 1} · ${(item.file.size / 1024 / 1024).toFixed(1)} MB`,
      );
      card.append(image, footer);
      previewList.append(card);
    });
    clearButton.disabled = files.length === 0;
    analyseButton.disabled = files.length === 0;
  };

  const addFiles = (incoming) => {
    resetResult();
    let rejection = "";
    for (const file of incoming) {
      if (files.length >= MAX_IMAGES) {
        rejection = "Use no more than four views from one study.";
        break;
      }
      if (!supportedTypes.has(file.type)) {
        rejection = "Use PNG, JPEG or WebP screenshots. Export DICOM images first.";
        continue;
      }
      if (file.size > MAX_BYTES) {
        rejection = "Each image must be 12 MB or smaller.";
        continue;
      }
      files.push({ file, url: URL.createObjectURL(file) });
    }
    renderPreviews();
    setStatus(
      rejection || `${files.length} view${files.length === 1 ? "" : "s"} ready.`,
      Boolean(rejection),
    );
  };

  const clearFiles = () => {
    files.forEach((item) => URL.revokeObjectURL(item.url));
    files.length = 0;
    input.value = "";
    renderPreviews();
    resetResult();
    setStatus("");
  };

  const appendList = (parent, title, items) => {
    if (!items || !items.length) return;
    const panel = create("div", "result-list");
    panel.append(create("h4", "", title));
    const list = create("ul");
    items.forEach((item) => list.append(create("li", "", item)));
    panel.append(list);
    parent.append(panel);
  };

  const categoryLabel = (category) => ({
    no_fracture_suspected: "No fracture suspected",
    possible_fracture: "Possible fracture",
    fracture_suspected: "Fracture suspected",
    indeterminate: "Indeterminate",
  }[category] || "Indeterminate");

  const renderBoxes = (svg, boxes) => {
    const namespace = "http://www.w3.org/2000/svg";
    (boxes || []).forEach((box, index) => {
      const colour = ["#38bdf8", "#f472b6", "#facc15"][index % 3];
      const rect = document.createElementNS(namespace, "rect");
      rect.setAttribute("x", box.x_min);
      rect.setAttribute("y", box.y_min);
      rect.setAttribute("width", box.x_max - box.x_min);
      rect.setAttribute("height", box.y_max - box.y_min);
      rect.setAttribute("fill", "none");
      rect.setAttribute("stroke", colour);
      rect.setAttribute("stroke-width", "7");
      rect.setAttribute("vector-effect", "non-scaling-stroke");
      const label = document.createElementNS(namespace, "text");
      label.setAttribute("x", Math.max(5, box.x_min + 8));
      label.setAttribute("y", Math.max(32, box.y_min - 10));
      label.setAttribute("fill", colour);
      label.setAttribute("font-size", "28");
      label.setAttribute("font-weight", "700");
      label.textContent = `${index + 1}: ${box.label}`;
      svg.append(rect, label);
    });
  };

  const renderResult = (payload) => {
    const assessment = payload.assessment;
    result.replaceChildren();

    const heading = create("div", "result-heading");
    const titleBlock = create("div");
    titleBlock.append(
      create("div", "eyebrow", "Live multi-view review"),
      create("h3", "", categoryLabel(assessment.assessment)),
    );
    const badge = create(
      "span",
      `assessment-badge ${assessment.assessment}`,
      `${assessment.confidence_percent}% model confidence`,
    );
    heading.append(titleBlock, badge);
    result.append(heading, create("p", "result-summary", assessment.summary));

    const columns = create("div", "result-columns");
    appendList(columns, "Key findings", assessment.key_findings);
    appendList(columns, "Limitations", assessment.limitations);
    result.append(columns);

    const viewGrid = create("div", "live-view-grid");
    [...assessment.views]
      .sort((a, b) => a.view_index - b.view_index)
      .forEach((view) => {
        const item = files[view.view_index - 1];
        if (!item) return;
        const card = create("article", "live-view-card");
        const shell = create("div", "live-image-shell");
        const image = create("img");
        image.src = item.url;
        image.alt = `Analysed X-ray view ${view.view_index}`;
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 1000 1000");
        svg.setAttribute("preserveAspectRatio", "none");
        renderBoxes(svg, view.boxes);
        shell.append(image, svg);
        const copy = create("div", "live-view-copy");
        copy.append(
          create("strong", "", `View ${view.view_index} · ${view.confidence_percent}% confidence`),
          create("span", "", view.summary),
        );
        card.append(shell, copy);
        viewGrid.append(card);
      });
    result.append(viewGrid);
    result.append(
      create(
        "p",
        "confidence-note",
        "Confidence is the model's subjective confidence in its wording, not a calibrated probability of fracture. Reassess the original diagnostic images yourself.",
      ),
    );
    result.hidden = false;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const analyse = async () => {
    if (!files.length || analyseButton.disabled) return;
    analyseButton.disabled = true;
    chooseButton.disabled = true;
    clearButton.disabled = true;
    resetResult();
    setStatus("Reviewing all views, then running a second visual critique…");
    const form = new FormData();
    files.forEach((item) => form.append("images", item.file, "xray-image"));
    const clinicalContext = contextInput.value.trim();
    if (clinicalContext) form.append("clinical_context", clinicalContext);

    try {
      const response = await fetch("/api/fracture-analysis", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      const payload = await response.json().catch(() => ({}));
      if (response.redirected && response.url.includes("/login")) {
        throw new Error("Your RadSpeed session has expired. Sign in again and retry.");
      }
      if (!response.ok) throw new Error(payload.detail || "The review could not be completed.");
      if (!payload.assessment) throw new Error("The review returned an incomplete result.");
      renderResult(payload);
      setStatus("Review complete. Interpret it alongside the original study.");
    } catch (error) {
      setStatus(error.message || "The review could not be completed.", true);
    } finally {
      analyseButton.disabled = files.length === 0;
      chooseButton.disabled = false;
      clearButton.disabled = files.length === 0;
    }
  };

  chooseButton.addEventListener("click", () => input.click());
  clearButton.addEventListener("click", clearFiles);
  analyseButton.addEventListener("click", analyse);
  input.addEventListener("change", () => addFiles(input.files));
  dropZone.addEventListener("click", () => input.click());
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("drag-over");
    addFiles(event.dataTransfer.files);
  });
  dropZone.addEventListener("paste", (event) => {
    const pasted = [...event.clipboardData.files].filter((file) => supportedTypes.has(file.type));
    if (pasted.length) {
      event.preventDefault();
      addFiles(pasted);
    }
  });
  window.addEventListener("beforeunload", () => {
    files.forEach((item) => URL.revokeObjectURL(item.url));
  });
})();
