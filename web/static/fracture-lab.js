(() => {
  "use strict";

  const MAX_IMAGES = 4;
  const MAX_BYTES = 12 * 1024 * 1024;
  const MAX_SOURCE_PIXELS = 24_000_000;
  const MAX_OUTPUT_EDGE = 3000;
  const MAX_OCR_EDGE = 2200;
  const supportedTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
  const safeImageMarkers = new Set([
    "L", "R", "AP", "PA", "LAT", "LATERAL", "OBL",
    "OBLIQUE", "WB", "ERECT", "SUPINE", "PORTABLE",
  ]);
  const contextIdentifierPattern = /\b(?:patient(?:\s*name)?|mrn|urn|dob|date\s+of\s+birth|accession|hospital\s*(?:id|number)|medicare)\s*[:#-]/i;
  const files = [];
  let nextFileId = 1;
  let privacyWorkerPromise = null;
  let privacyQueue = Promise.resolve();
  let analysisBusy = false;

  const byId = (id) => document.getElementById(id);
  const input = byId("fracture-file-input");
  const dropZone = byId("fracture-drop-zone");
  const previewList = byId("fracture-preview-list");
  const chooseButton = byId("fracture-choose");
  const clearButton = byId("fracture-clear");
  const analyseButton = byId("fracture-analyse");
  const contextInput = byId("fracture-context");
  const privacyPanel = byId("fracture-privacy-panel");
  const privacySummary = byId("fracture-privacy-summary");
  const privacyConfirm = byId("fracture-privacy-confirm");
  const status = byId("fracture-status");
  const result = byId("fracture-result");

  if (
    !input || !dropZone || !previewList || !analyseButton || !result ||
    !privacyPanel || !privacySummary || !privacyConfirm
  ) return;

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

  const revokeUrl = (url) => {
    if (url) URL.revokeObjectURL(url);
  };

  const releaseItem = (item) => {
    item.removed = true;
    revokeUrl(item.originalUrl);
    revokeUrl(item.scrubbedUrl);
    item.sourceCanvas = null;
    item.scrubbedFile = null;
  };

  const stateIsReviewable = (item) => (
    item.state === "ready" || item.state === "manual_required"
  ) && Boolean(item.scrubbedFile);

  const allPrivacyReady = () => files.length > 0 && files.every(stateIsReviewable);

  const updateControls = () => {
    const privacyReady = allPrivacyReady();
    clearButton.disabled = analysisBusy || files.length === 0;
    chooseButton.disabled = analysisBusy || files.length >= MAX_IMAGES;
    privacyConfirm.disabled = analysisBusy || !privacyReady;
    analyseButton.disabled = (
      analysisBusy || !privacyReady || !privacyConfirm.checked
    );
  };

  const updatePrivacySummary = () => {
    privacyPanel.hidden = files.length === 0;
    if (!files.length) {
      privacySummary.textContent = "";
      updateControls();
      return;
    }
    const working = files.filter((item) => ["queued", "loading", "checking"].includes(item.state));
    const failed = files.filter((item) => item.state === "error");
    const manual = files.filter((item) => item.state === "manual_required");
    const covered = files.reduce((total, item) => total + item.redactions.length, 0);
    if (failed.length) {
      privacySummary.textContent = "One image could not be prepared. Remove it and try another screenshot.";
    } else if (working.length) {
      privacySummary.textContent = `Checking ${working.length} image${working.length === 1 ? "" : "s"} for visible text on this device…`;
    } else if (manual.length) {
      privacySummary.textContent = `Automatic text recognition was unavailable for ${manual.length} image${manual.length === 1 ? "" : "s"}. Inspect the previews carefully and drag over any identifiers.`;
    } else if (covered) {
      privacySummary.textContent = `${covered} text area${covered === 1 ? "" : "s"} covered locally. Check the cleaned previews before analysis.`;
    } else {
      privacySummary.textContent = "No removable text was detected. Check the previews in case anything was missed.";
    }
    updateControls();
  };

  const drawScrubbed = (context, item, draft = null) => {
    if (!item.sourceCanvas) return;
    context.clearRect(0, 0, context.canvas.width, context.canvas.height);
    context.drawImage(item.sourceCanvas, 0, 0);
    context.fillStyle = "#000";
    item.redactions.forEach((box) => {
      context.fillRect(box.x, box.y, box.width, box.height);
    });
    if (draft) {
      context.fillStyle = "rgba(0, 0, 0, .72)";
      context.fillRect(draft.x, draft.y, draft.width, draft.height);
      context.strokeStyle = "#60a5fa";
      context.lineWidth = Math.max(2, Math.round(context.canvas.width / 700));
      context.strokeRect(draft.x, draft.y, draft.width, draft.height);
    }
  };

  const canvasToBlob = (canvas, type, quality) => new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The cleaned image could not be created."));
    }, type, quality);
  });

  const refreshScrubbedFile = async (item) => {
    if (item.removed || !item.sourceCanvas) return;
    const canvas = document.createElement("canvas");
    canvas.width = item.sourceCanvas.width;
    canvas.height = item.sourceCanvas.height;
    drawScrubbed(canvas.getContext("2d", { alpha: false }), item);

    let outputType = item.sourceType === "image/png" ? "image/png" : "image/jpeg";
    let blob = await canvasToBlob(canvas, outputType, 0.98);
    if (blob.size > MAX_BYTES && outputType === "image/png") {
      outputType = "image/jpeg";
      blob = await canvasToBlob(canvas, outputType, 0.98);
    }
    if (blob.size > MAX_BYTES) {
      throw new Error("The cleaned image is larger than 12 MB. Crop it and try again.");
    }
    if (item.removed) return;

    revokeUrl(item.scrubbedUrl);
    const extension = outputType === "image/png" ? "png" : "jpg";
    item.scrubbedFile = new File(
      [blob],
      `deidentified-view-${item.id}.${extension}`,
      { type: outputType, lastModified: Date.now() },
    );
    item.scrubbedUrl = URL.createObjectURL(blob);
  };

  const loadImageCanvas = async (file) => {
    let imageSource;
    let cleanup = () => {};
    if ("createImageBitmap" in window) {
      imageSource = await createImageBitmap(file);
      cleanup = () => imageSource.close();
    } else {
      const url = URL.createObjectURL(file);
      imageSource = await new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => {
          URL.revokeObjectURL(url);
          reject(new Error("The screenshot could not be decoded."));
        };
        image.src = url;
      });
      cleanup = () => URL.revokeObjectURL(url);
    }

    const width = imageSource.naturalWidth || imageSource.width;
    const height = imageSource.naturalHeight || imageSource.height;
    if (!width || !height || width < 64 || height < 64) {
      cleanup();
      throw new Error("The screenshot is too small to analyse.");
    }
    if (width * height > MAX_SOURCE_PIXELS) {
      cleanup();
      throw new Error("The screenshot is larger than 24 megapixels. Crop or resize it and try again.");
    }
    const scale = Math.min(1, MAX_OUTPUT_EDGE / Math.max(width, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    canvas.getContext("2d", { alpha: false }).drawImage(
      imageSource, 0, 0, canvas.width, canvas.height,
    );
    cleanup();
    return canvas;
  };

  const createOcrCanvas = (sourceCanvas) => {
    const scale = Math.min(1, MAX_OCR_EDGE / Math.max(sourceCanvas.width, sourceCanvas.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(sourceCanvas.width * scale));
    canvas.height = Math.max(1, Math.round(sourceCanvas.height * scale));
    canvas.getContext("2d", { alpha: false }).drawImage(
      sourceCanvas, 0, 0, canvas.width, canvas.height,
    );
    return { canvas, scale };
  };

  const normaliseMarker = (text) => text.toUpperCase().replace(/[^A-Z]/g, "");

  const parseTsvWords = (tsv) => {
    if (!tsv) return [];
    return tsv.split(/\r?\n/).slice(1).flatMap((line) => {
      const cells = line.split("\t");
      if (cells.length < 12 || cells[0] !== "5") return [];
      const text = cells.slice(11).join("\t").trim();
      const confidence = Number(cells[10]);
      const left = Number(cells[6]);
      const top = Number(cells[7]);
      const width = Number(cells[8]);
      const height = Number(cells[9]);
      if (!text || ![confidence, left, top, width, height].every(Number.isFinite)) return [];
      return [{ text, confidence, left, top, width, height }];
    });
  };

  const shouldRedactWord = (word, width, height) => {
    const marker = normaliseMarker(word.text);
    if (safeImageMarkers.has(marker)) return false;
    if (!/[A-Za-z0-9]/.test(word.text) || word.width < 2 || word.height < 2) return false;

    const nearEdge = (
      word.left < width * 0.22 || word.left + word.width > width * 0.78 ||
      word.top < height * 0.25 || word.top + word.height > height * 0.80
    );
    const sensitiveLabel = /^(?:PATIENT|NAME|DOB|BIRTH|MRN|URN|ID|ACCESSION|ACC|HOSPITAL|MEDICARE)/.test(marker);
    const usefulLength = marker.length >= 2 || /\d{2,}/.test(word.text);
    return sensitiveLabel || (usefulLength && word.confidence >= (nearEdge ? 22 : 45));
  };

  const redactionsFromTsv = (tsv, ocrWidth, ocrHeight, scale) => {
    const sourceWidth = ocrWidth / scale;
    const sourceHeight = ocrHeight / scale;
    return parseTsvWords(tsv)
      .filter((word) => shouldRedactWord(word, ocrWidth, ocrHeight))
      .map((word) => {
        const padding = Math.max(4, Math.round(word.height * 0.22));
        const left = Math.max(0, word.left - padding);
        const top = Math.max(0, word.top - padding);
        const right = Math.min(ocrWidth, word.left + word.width + padding);
        const bottom = Math.min(ocrHeight, word.top + word.height + padding);
        return {
          x: Math.round(left / scale),
          y: Math.round(top / scale),
          width: Math.min(Math.round((right - left) / scale), Math.round(sourceWidth)),
          height: Math.min(Math.round((bottom - top) / scale), Math.round(sourceHeight)),
          source: "automatic",
        };
      });
  };

  const getPrivacyWorker = async () => {
    if (!privacyWorkerPromise) {
      if (!window.Tesseract || !window.Tesseract.createWorker) {
        throw new Error("Local text recognition did not load.");
      }
      privacyWorkerPromise = window.Tesseract.createWorker("eng", 1, {
        workerPath: "/static/vendor/tesseract/worker.min.js",
        langPath: "/static/vendor/tesseract/",
        corePath: "/static/vendor/tesseract/tesseract-core-lstm.wasm.js",
      });
    }
    return privacyWorkerPromise;
  };

  const describeItemState = (item) => {
    if (item.state === "queued" || item.state === "loading") return "Preparing locally…";
    if (item.state === "checking") return "Checking visible text locally…";
    if (item.state === "manual_required") return "Automatic check unavailable · inspect manually";
    if (item.state === "error") return item.error || "Could not prepare image";
    if (item.redactions.length) {
      return `${item.redactions.length} area${item.redactions.length === 1 ? "" : "s"} covered`;
    }
    return "No text detected · inspect for anything missed";
  };

  const pointerPosition = (event, canvas) => {
    const bounds = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, (event.clientX - bounds.left) * canvas.width / bounds.width)),
      y: Math.max(0, Math.min(canvas.height, (event.clientY - bounds.top) * canvas.height / bounds.height)),
    };
  };

  const attachRedactionDrawing = (canvas, item) => {
    let start = null;
    let draft = null;
    const redraw = () => drawScrubbed(canvas.getContext("2d", { alpha: false }), item, draft);

    canvas.addEventListener("pointerdown", (event) => {
      if (analysisBusy || !stateIsReviewable(item)) return;
      event.preventDefault();
      privacyConfirm.checked = false;
      start = pointerPosition(event, canvas);
      draft = { x: start.x, y: start.y, width: 0, height: 0 };
      canvas.setPointerCapture(event.pointerId);
      updateControls();
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!start) return;
      const point = pointerPosition(event, canvas);
      draft = {
        x: Math.min(start.x, point.x),
        y: Math.min(start.y, point.y),
        width: Math.abs(point.x - start.x),
        height: Math.abs(point.y - start.y),
      };
      redraw();
    });
    canvas.addEventListener("pointerup", async (event) => {
      if (!start || !draft) return;
      canvas.releasePointerCapture(event.pointerId);
      const finished = draft;
      start = null;
      draft = null;
      if (finished.width < 3 || finished.height < 3) {
        redraw();
        return;
      }
      item.redactions.push({
        x: Math.round(finished.x),
        y: Math.round(finished.y),
        width: Math.round(finished.width),
        height: Math.round(finished.height),
        source: "manual",
      });
      try {
        await refreshScrubbedFile(item);
        setStatus("Manual blackout added. Check the cleaned preview, then confirm privacy.");
      } catch (error) {
        item.state = "error";
        item.error = error.message;
        setStatus(error.message, true);
      }
      renderPreviews();
    });
    canvas.addEventListener("pointercancel", () => {
      start = null;
      draft = null;
      redraw();
    });
  };

  const renderPreviews = () => {
    previewList.replaceChildren();
    files.forEach((item, index) => {
      const card = create("article", `fracture-preview privacy-${item.state}`);
      card.dataset.fileId = String(item.id);
      const shell = create("div", "fracture-preview-shell");
      if (item.sourceCanvas) {
        const canvas = create("canvas", "fracture-preview-canvas");
        canvas.width = item.sourceCanvas.width;
        canvas.height = item.sourceCanvas.height;
        canvas.setAttribute("aria-label", `Cleaned X-ray view ${index + 1}. Drag to black out anything missed.`);
        drawScrubbed(canvas.getContext("2d", { alpha: false }), item);
        attachRedactionDrawing(canvas, item);
        shell.append(canvas);
      } else {
        const image = create("img");
        image.src = item.originalUrl;
        image.alt = `Selected X-ray view ${index + 1}`;
        shell.append(image);
      }
      if (["queued", "loading", "checking"].includes(item.state)) {
        shell.append(create("div", "privacy-working", "Private check running…"));
      }

      const footer = create("div", "fracture-preview-footer");
      const copy = create("div");
      copy.append(
        create("strong", "", `View ${index + 1}`),
        create("span", item.state === "error" ? "privacy-state error" : "privacy-state", describeItemState(item)),
      );
      const controls = create("div", "privacy-image-actions");
      const undo = create("button", "privacy-mini-button", "Undo blackout");
      undo.type = "button";
      undo.disabled = analysisBusy || !item.redactions.some((box) => box.source === "manual");
      undo.addEventListener("click", async () => {
        const lastManual = item.redactions.findLastIndex((box) => box.source === "manual");
        if (lastManual < 0) return;
        item.redactions.splice(lastManual, 1);
        privacyConfirm.checked = false;
        try {
          await refreshScrubbedFile(item);
          setStatus("Last manual blackout removed. Check the preview again.");
        } catch (error) {
          item.state = "error";
          item.error = error.message;
          setStatus(error.message, true);
        }
        renderPreviews();
      });
      const remove = create("button", "privacy-mini-button danger", "Remove");
      remove.type = "button";
      remove.disabled = analysisBusy;
      remove.addEventListener("click", () => {
        const fileIndex = files.indexOf(item);
        if (fileIndex < 0) return;
        files.splice(fileIndex, 1);
        releaseItem(item);
        privacyConfirm.checked = false;
        resetResult();
        renderPreviews();
        setStatus(files.length ? "Image removed. Check the remaining cleaned previews." : "");
      });
      controls.append(undo, remove);
      footer.append(copy, controls);
      card.append(shell, footer);
      previewList.append(card);
    });
    updatePrivacySummary();
  };

  const processItem = async (item) => {
    if (item.removed) return;
    try {
      item.state = "loading";
      renderPreviews();
      item.sourceCanvas = await loadImageCanvas(item.file);
      if (item.removed) return;
      revokeUrl(item.originalUrl);
      item.originalUrl = null;
      item.file = null;
      await refreshScrubbedFile(item);
      item.state = "checking";
      renderPreviews();

      try {
        const worker = await getPrivacyWorker();
        const { canvas, scale } = createOcrCanvas(item.sourceCanvas);
        const recognition = await worker.recognize(
          canvas,
          { tessedit_pageseg_mode: "11", user_defined_dpi: "300" },
          { text: true, tsv: true },
        );
        item.redactions.push(...redactionsFromTsv(
          recognition.data.tsv,
          canvas.width,
          canvas.height,
          scale,
        ));
        item.state = "ready";
      } catch (error) {
        console.warn("Local privacy text recognition unavailable; manual review required.");
        item.state = "manual_required";
      }
      if (item.removed) return;
      await refreshScrubbedFile(item);
      if (item.removed) return;
      renderPreviews();
      if (files.every(stateIsReviewable)) {
        setStatus("Local privacy check complete. Inspect each cleaned preview and confirm below.");
      }
    } catch (error) {
      if (item.removed) return;
      item.state = "error";
      item.error = error.message || "The screenshot could not be prepared.";
      renderPreviews();
      setStatus(item.error, true);
    }
  };

  const addFiles = (incoming) => {
    resetResult();
    privacyConfirm.checked = false;
    let rejection = "";
    const added = [];
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
      const item = {
        id: nextFileId++,
        file,
        sourceType: file.type,
        originalUrl: URL.createObjectURL(file),
        scrubbedUrl: null,
        scrubbedFile: null,
        sourceCanvas: null,
        redactions: [],
        state: "queued",
        error: "",
        removed: false,
      };
      files.push(item);
      added.push(item);
    }
    input.value = "";
    renderPreviews();
    setStatus(
      rejection || (added.length ? "Preparing images and checking visible text locally…" : ""),
      Boolean(rejection),
    );
    added.forEach((item) => {
      privacyQueue = privacyQueue.then(() => processItem(item));
    });
  };

  const clearFiles = () => {
    files.forEach(releaseItem);
    files.length = 0;
    input.value = "";
    privacyConfirm.checked = false;
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

  const renderBoxes = (svg, boxes, { supporting = false } = {}) => {
    const namespace = "http://www.w3.org/2000/svg";
    (boxes || []).forEach((box, index) => {
      const colour = supporting
        ? "#34d399"
        : ["#38bdf8", "#f472b6", "#facc15"][index % 3];
      const rect = document.createElementNS(namespace, "rect");
      rect.setAttribute("x", box.x_min);
      rect.setAttribute("y", box.y_min);
      rect.setAttribute("width", box.x_max - box.x_min);
      rect.setAttribute("height", box.y_max - box.y_min);
      rect.setAttribute("fill", "none");
      rect.setAttribute("stroke", colour);
      rect.setAttribute("stroke-width", "7");
      rect.setAttribute("vector-effect", "non-scaling-stroke");
      if (supporting) rect.setAttribute("stroke-dasharray", "18 12");
      const label = document.createElementNS(namespace, "text");
      label.setAttribute("x", Math.max(5, box.x_min + 8));
      label.setAttribute("y", Math.max(32, box.y_min - 10));
      label.setAttribute("fill", colour);
      label.setAttribute("font-size", "28");
      label.setAttribute("font-weight", "700");
      label.textContent = supporting
        ? `Open model ${index + 1}: attention cue`
        : `${index + 1}: ${box.label}`;
      svg.append(rect, label);
    });
  };

  const renderSupportingModels = (models) => {
    if (!models.length) return null;
    const section = create("section", "supporting-models");
    section.append(
      create("h4", "", "Independent open models"),
      create(
        "p",
        "supporting-model-intro",
        "These ran separately after the frontier read. Their outputs were not shown to it or automatically combined with its answer.",
      ),
    );
    const grid = create("div", "supporting-model-grid");
    models.forEach((model) => {
      const card = create("article", "supporting-model-card");
      card.append(
        create("strong", "", model.label || "Open model"),
        create("span", "model-scope", model.scope || "Public-data research model"),
      );
      if (model.kind === "classifier") {
        const viewScores = (model.view_probabilities || [])
          .map((probability, index) => `view ${index + 1}: ${Math.round(probability * 100)}%`)
          .join(" · ");
        card.append(
          create(
            "p",
            "model-result",
            `Public-dataset fracture estimate: ${Math.round(model.highest_view_probability * 100)}% on the highest view.`,
          ),
        );
        if (viewScores) card.append(create("p", "model-detail", viewScores));
      } else if (model.kind === "locator") {
        const boxCount = (model.views || []).reduce(
          (total, view) => total + (view.boxes || []).length,
          0,
        );
        card.append(
          create(
            "p",
            "model-result",
            boxCount
              ? `${boxCount} dashed green attention cue${boxCount === 1 ? "" : "s"} shown on the images.`
              : "No attention cues were suggested.",
          ),
        );
      }
      if (model.evaluation) {
        card.append(
          create(
            "p",
            "model-evidence",
            `Research check: AUC ${Number(model.evaluation.auc).toFixed(3)} on ${model.evaluation.cases} public images. ${model.evaluation.limitation}`,
          ),
        );
      }
      grid.append(card);
    });
    section.append(grid);
    return section;
  };

  const renderResult = (payload) => {
    const assessment = payload.assessment;
    result.replaceChildren();

    const heading = create("div", "result-heading");
    const titleBlock = create("div");
    titleBlock.append(
      create("div", "eyebrow", "Frontier model · independent read"),
      create("h3", "", categoryLabel(assessment.assessment)),
    );
    const badge = create(
      "span",
      `assessment-badge ${assessment.assessment}`,
      `${assessment.confidence_percent}% model confidence`,
    );
    heading.append(titleBlock, badge);
    result.append(heading, create("p", "result-summary", assessment.summary));

    const supportingModels = payload.supporting_models || [];
    const supportingSection = renderSupportingModels(supportingModels);
    if (supportingSection) result.append(supportingSection);

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
        image.src = item.scrubbedUrl;
        image.alt = `Analysed de-identified X-ray view ${view.view_index}`;
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 1000 1000");
        svg.setAttribute("preserveAspectRatio", "none");
        renderBoxes(svg, view.boxes);
        const supportingBoxes = supportingModels
          .filter((model) => model.kind === "locator")
          .flatMap((model) => {
            const locatorView = (model.views || []).find(
              (candidate) => candidate.view_index === view.view_index,
            );
            return locatorView ? locatorView.boxes || [] : [];
          });
        renderBoxes(svg, supportingBoxes, { supporting: true });
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
        "Frontier confidence is subjective confidence in its wording, not fracture probability. Open-model estimates and dashed boxes are separate supporting opinions. Reassess the original diagnostic images yourself.",
      ),
    );
    result.hidden = false;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const analyse = async () => {
    if (!files.length || analyseButton.disabled) return;
    const clinicalContext = contextInput.value.trim();
    if (contextIdentifierPattern.test(clinicalContext)) {
      setStatus("The clinical context appears to contain a patient identifier. Remove it before analysis.", true);
      contextInput.focus();
      return;
    }

    analysisBusy = true;
    updateControls();
    resetResult();
    setStatus("Uploading only the cleaned copies, then running one frontier read and a separate open-model check…");
    const form = new FormData();
    files.forEach((item) => form.append("images", item.scrubbedFile, item.scrubbedFile.name));
    form.append("privacy_confirmed", "true");
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
      analysisBusy = false;
      updateControls();
    }
  };

  chooseButton.addEventListener("click", () => input.click());
  clearButton.addEventListener("click", clearFiles);
  analyseButton.addEventListener("click", analyse);
  privacyConfirm.addEventListener("change", updateControls);
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
    files.forEach(releaseItem);
    if (privacyWorkerPromise) {
      privacyWorkerPromise.then((worker) => worker.terminate()).catch(() => {});
    }
  });
})();
