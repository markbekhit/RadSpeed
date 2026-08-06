(() => {
  "use strict";

  const MAX_IMAGES = 4;
  const MAX_BYTES = 12 * 1024 * 1024;
  const MAX_DICOM_BYTES = 64 * 1024 * 1024;
  const MAX_ZIP_BYTES = 256 * 1024 * 1024;
  const MAX_ZIP_ENTRIES = 10_000;
  const MAX_ZIP_EXPANDED_BYTES = MAX_DICOM_BYTES * MAX_IMAGES;
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
  let importBusy = false;

  const byId = (id) => document.getElementById(id);
  const input = byId("fracture-file-input");
  const folderInput = byId("fracture-folder-input");
  const dropZone = byId("fracture-drop-zone");
  const previewList = byId("fracture-preview-list");
  const chooseButton = byId("fracture-choose");
  const chooseFolderButton = byId("fracture-choose-folder");
  const clearButton = byId("fracture-clear");
  const analyseButton = byId("fracture-analyse");
  const contextInput = byId("fracture-context");
  const privacyPanel = byId("fracture-privacy-panel");
  const privacySummary = byId("fracture-privacy-summary");
  const privacyConfirm = byId("fracture-privacy-confirm");
  const status = byId("fracture-status");
  const result = byId("fracture-result");

  if (
    !input || !folderInput || !dropZone || !previewList || !analyseButton || !result ||
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
    clearButton.disabled = analysisBusy || importBusy || files.length === 0;
    chooseButton.disabled = analysisBusy || importBusy || files.length >= MAX_IMAGES;
    chooseFolderButton.disabled = analysisBusy || importBusy || files.length >= MAX_IMAGES;
    privacyConfirm.disabled = analysisBusy || importBusy || !privacyReady;
    analyseButton.disabled = (
      analysisBusy || importBusy || !privacyReady || !privacyConfirm.checked
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

  const isDicomCandidate = (file) => {
    const name = (file.name || "").toLowerCase();
    return name.endsWith(".dcm") || name.endsWith(".dicom") || name.endsWith(".ima") ||
      file.type === "application/dicom" ||
      file.type === "application/dicom+binary" ||
      (!file.type || file.type === "application/octet-stream");
  };

  const isZipCandidate = (file) => {
    const name = (file.name || "").toLowerCase();
    return name.endsWith(".zip") || file.type === "application/zip" ||
      file.type === "application/x-zip-compressed";
  };

  const zipEntryType = (name) => {
    const lower = name.toLowerCase();
    if (lower.endsWith(".png")) return "image/png";
    if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
    if (lower.endsWith(".webp")) return "image/webp";
    if (lower.endsWith(".dcm") || lower.endsWith(".dicom") || lower.endsWith(".ima")) {
      return "application/dicom";
    }
    return "application/octet-stream";
  };

  const looksLikeDicom = (contents) => {
    if (contents.length >= 132 && String.fromCharCode(...contents.slice(128, 132)) === "DICM") {
      return true;
    }
    return contents.length >= 8 && contents[1] === 0 && [0x02, 0x08, 0x10, 0x28].includes(contents[0]);
  };

  const inflateZipEntry = async (contents) => {
    if (!("DecompressionStream" in window)) {
      throw new Error("This browser cannot open compressed ZIP files. Choose the folder instead.");
    }
    try {
      const reader = new Blob([contents]).stream()
        .pipeThrough(new DecompressionStream("deflate-raw"))
        .getReader();
      const chunks = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > MAX_DICOM_BYTES) {
          await reader.cancel();
          throw new Error("Each file inside the ZIP must be 64 MB or smaller.");
        }
        chunks.push(value);
      }
      return new Uint8Array(await new Blob(chunks).arrayBuffer());
    } catch (error) {
      if (error.message?.includes("64 MB")) throw error;
      throw new Error("A file inside this ZIP could not be decompressed.");
    }
  };

  const readZipEntries = async (file) => {
    if (file.size > MAX_ZIP_BYTES) {
      throw new Error("The ZIP must be 256 MB or smaller.");
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const minimumEocdOffset = Math.max(0, bytes.length - 65_557);
    let eocdOffset = -1;
    for (let offset = bytes.length - 22; offset >= minimumEocdOffset; offset -= 1) {
      if (view.getUint32(offset, true) === 0x06054b50) {
        eocdOffset = offset;
        break;
      }
    }
    if (eocdOffset < 0) throw new Error("This ZIP could not be opened.");
    const diskNumber = view.getUint16(eocdOffset + 4, true);
    const centralDisk = view.getUint16(eocdOffset + 6, true);
    const entryCount = view.getUint16(eocdOffset + 10, true);
    const centralOffset = view.getUint32(eocdOffset + 16, true);
    if (diskNumber || centralDisk) throw new Error("Multi-part ZIP files are not supported.");
    if (entryCount === 0xffff || entryCount > MAX_ZIP_ENTRIES) {
      throw new Error("This ZIP contains too many files.");
    }

    const decoder = new TextDecoder("utf-8");
    const entries = [];
    let offset = centralOffset;
    for (let index = 0; index < entryCount; index += 1) {
      if (offset + 46 > bytes.length || view.getUint32(offset, true) !== 0x02014b50) {
        throw new Error("This ZIP's file list is damaged.");
      }
      const flags = view.getUint16(offset + 8, true);
      const method = view.getUint16(offset + 10, true);
      const compressedSize = view.getUint32(offset + 20, true);
      const expandedSize = view.getUint32(offset + 24, true);
      const nameLength = view.getUint16(offset + 28, true);
      const extraLength = view.getUint16(offset + 30, true);
      const commentLength = view.getUint16(offset + 32, true);
      const localOffset = view.getUint32(offset + 42, true);
      const end = offset + 46 + nameLength + extraLength + commentLength;
      if (end > bytes.length) throw new Error("This ZIP's file list is damaged.");
      const name = decoder.decode(bytes.subarray(offset + 46, offset + 46 + nameLength));
      offset = end;

      const basename = name.split("/").filter(Boolean).at(-1) || "";
      if (!basename || name.endsWith("/") || name.startsWith("__MACOSX/") ||
          basename === ".DS_Store" || basename.toUpperCase() === "DICOMDIR") continue;
      entries.push({ name: basename, flags, method, compressedSize, expandedSize, localOffset });
    }

    const extracted = [];
    let inspected = 0;
    let expandedBytes = 0;
    for (const entry of entries) {
      if (extracted.length >= MAX_IMAGES) break;
      inspected += 1;
      if (entry.flags & 1) throw new Error("Password-protected ZIP files are not supported.");
      if (![0, 8].includes(entry.method)) {
        throw new Error("This ZIP uses an unsupported compression format.");
      }
      if (entry.expandedSize > MAX_DICOM_BYTES) {
        throw new Error("Each file inside the ZIP must be 64 MB or smaller.");
      }
      expandedBytes += entry.expandedSize;
      if (expandedBytes > MAX_ZIP_EXPANDED_BYTES) {
        throw new Error("The files inside the ZIP are too large to open safely.");
      }
      if (entry.localOffset + 30 > bytes.length ||
          view.getUint32(entry.localOffset, true) !== 0x04034b50) {
        throw new Error("This ZIP contains a damaged file.");
      }
      const localNameLength = view.getUint16(entry.localOffset + 26, true);
      const localExtraLength = view.getUint16(entry.localOffset + 28, true);
      const dataStart = entry.localOffset + 30 + localNameLength + localExtraLength;
      const dataEnd = dataStart + entry.compressedSize;
      if (dataEnd > bytes.length) throw new Error("This ZIP contains a damaged file.");
      let contents = bytes.slice(dataStart, dataEnd);
      if (entry.method === 8) {
        contents = await inflateZipEntry(contents);
      }
      if (contents.length !== entry.expandedSize) {
        throw new Error("A file inside this ZIP is incomplete.");
      }
      const type = zipEntryType(entry.name);
      if (type === "application/octet-stream" && !looksLikeDicom(contents)) continue;
      extracted.push(new File([contents], entry.name, { type }));
    }
    if (!extracted.length) {
      throw new Error("No supported DICOM or image files were found in this ZIP.");
    }
    return { extracted, omitted: Math.max(0, entries.length - inspected) };
  };

  const dicomWindow = (image, pixels) => {
    const photometric = String(image.getPhotometricInterpretation() || "").toUpperCase();
    const center = Number(image.getWindowCenter());
    const width = Number(image.getWindowWidth());
    if (photometric !== "MONOCHROME1" && Number.isFinite(center) && Number.isFinite(width) && width > 1) {
      return { low: center - 0.5 - (width - 1) / 2, high: center - 0.5 + (width - 1) / 2 };
    }

    const stride = Math.max(1, Math.floor(pixels.length / 100_000));
    const sample = [];
    for (let index = 0; index < pixels.length; index += stride) sample.push(pixels[index]);
    sample.sort((a, b) => a - b);
    const low = sample[Math.floor((sample.length - 1) * 0.005)];
    const high = sample[Math.ceil((sample.length - 1) * 0.995)];
    return high > low ? { low, high } : { low: low - 0.5, high: high + 0.5 };
  };

  const renderDicomFrame = (image, frameIndex, width, height) => {
    const interpreted = image.getInterpretedData(false, true, frameIndex);
    const pixels = interpreted?.data;
    if (!pixels || pixels.length !== width * height) {
      throw new Error("This DICOM image layout is not supported.");
    }
    const { low, high } = dicomWindow(image, pixels);
    const range = high - low;
    const nativeCanvas = document.createElement("canvas");
    nativeCanvas.width = width;
    nativeCanvas.height = height;
    const context = nativeCanvas.getContext("2d", { alpha: false });
    const imageData = context.createImageData(width, height);
    for (let source = 0, target = 0; source < pixels.length; source += 1, target += 4) {
      const grey = Math.max(0, Math.min(255, Math.round((pixels[source] - low) * 255 / range)));
      imageData.data[target] = grey;
      imageData.data[target + 1] = grey;
      imageData.data[target + 2] = grey;
      imageData.data[target + 3] = 255;
    }
    context.putImageData(imageData, 0, 0);

    const scale = Math.min(1, MAX_OUTPUT_EDGE / Math.max(width, height));
    if (scale === 1) return nativeCanvas;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    canvas.getContext("2d", { alpha: false }).drawImage(nativeCanvas, 0, 0, canvas.width, canvas.height);
    return canvas;
  };

  const loadDicomCanvases = async (file, limit) => {
    if (!window.daikon?.Series?.parseImage) {
      throw new Error("Local DICOM support did not load. Refresh the page and try again.");
    }
    const buffer = await file.arrayBuffer();
    window.daikon.Parser.verbose = false;
    let image;
    try {
      image = window.daikon.Series.parseImage(new DataView(buffer));
    } catch (_error) {
      throw new Error("This DICOM file could not be decoded.");
    }
    if (!image || !image.hasPixelData()) {
      throw new Error("This DICOM does not contain an image.");
    }
    const photometric = String(image.getPhotometricInterpretation() || "").toUpperCase();
    if (!photometric.startsWith("MONOCHROME") || Number(image.getNumberOfSamplesPerPixel()) !== 1) {
      throw new Error("Fracture Lab currently supports monochrome radiograph DICOMs only.");
    }
    const width = Number(image.getCols());
    const height = Number(image.getRows());
    if (!width || !height || width < 64 || height < 64) {
      throw new Error("The DICOM image is too small to analyse.");
    }
    if (width * height > MAX_SOURCE_PIXELS) {
      throw new Error("The DICOM image is larger than 24 megapixels.");
    }
    const frameCount = Math.max(1, Number(image.getNumberOfFrames()) || 1);
    const canvases = [];
    for (let frameIndex = 0; frameIndex < Math.min(frameCount, limit); frameIndex += 1) {
      canvases.push(renderDicomFrame(image, frameIndex, width, height));
    }
    return { canvases, frameCount };
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
      return [{
        text,
        confidence,
        left,
        top,
        width,
        height,
        lineKey: cells.slice(1, 5).join(":"),
      }];
    });
  };

  const isSensitiveLabel = (word) => {
    const marker = normaliseMarker(word.text);
    return /^(?:PATIENT|PATIENTNAME|NAME|DOB|DATEOFBIRTH|BIRTHDATE|MRN|URN|NHI|IHI|PID|UHID|ID|PATIENTID|ACCESSION|ACCESSIONNUMBER|ACCNO|MEDICARE)$/.test(marker);
  };

  const shouldRedactStandaloneIdentifier = (word, width, height) => {
    const marker = normaliseMarker(word.text);
    if (safeImageMarkers.has(marker)) return false;
    if (!/[A-Za-z0-9]/.test(word.text) || word.width < 2 || word.height < 2) return false;
    const nearEdge = (
      word.left < width * 0.22 || word.left + word.width > width * 0.78 ||
      word.top < height * 0.25 || word.top + word.height > height * 0.80
    );
    if (!nearEdge || word.confidence < 55) return false;
    const compact = word.text.toUpperCase().replace(/[^A-Z0-9]/g, "");
    const digitCount = (compact.match(/\d/g) || []).length;
    const hasLetters = /[A-Z]/.test(compact);
    const dateLike = /^(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})$/.test(word.text.trim());
    return dateLike || digitCount >= 6 || (hasLetters && digitCount >= 4 && compact.length >= 7);
  };

  const redactionsFromTsv = (tsv, ocrWidth, ocrHeight, scale) => {
    const sourceWidth = ocrWidth / scale;
    const sourceHeight = ocrHeight / scale;
    const words = parseTsvWords(tsv);
    const sensitiveLines = new Set(
      words.filter(isSensitiveLabel).map((word) => word.lineKey),
    );
    const groups = [];

    sensitiveLines.forEach((lineKey) => {
      const lineWords = words.filter((word) => (
        word.lineKey === lineKey && word.confidence >= 20 &&
        /[A-Za-z0-9]/.test(word.text) && !safeImageMarkers.has(normaliseMarker(word.text))
      ));
      if (lineWords.length) groups.push(lineWords);
    });
    words
      .filter((word) => !sensitiveLines.has(word.lineKey))
      .filter((word) => shouldRedactStandaloneIdentifier(word, ocrWidth, ocrHeight))
      .forEach((word) => groups.push([word]));

    return groups.map((group) => {
      const leftEdge = Math.min(...group.map((word) => word.left));
      const topEdge = Math.min(...group.map((word) => word.top));
      const rightEdge = Math.max(...group.map((word) => word.left + word.width));
      const bottomEdge = Math.max(...group.map((word) => word.top + word.height));
      const padding = Math.max(4, Math.round((bottomEdge - topEdge) * 0.22));
      const left = Math.max(0, leftEdge - padding);
      const top = Math.max(0, topEdge - padding);
      const right = Math.min(ocrWidth, rightEdge + padding);
      const bottom = Math.min(ocrHeight, bottomEdge + padding);
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

    canvas.addEventListener("pointerdown", async (event) => {
      if (analysisBusy || !stateIsReviewable(item)) return;
      event.preventDefault();
      privacyConfirm.checked = false;
      const point = pointerPosition(event, canvas);
      const selectedIndex = item.redactions.findLastIndex((box) => (
        point.x >= box.x && point.x <= box.x + box.width &&
        point.y >= box.y && point.y <= box.y + box.height
      ));
      if (selectedIndex >= 0) {
        item.redactions.splice(selectedIndex, 1);
        try {
          await refreshScrubbedFile(item);
          setStatus("Blackout removed. Check the preview again, then confirm privacy.");
        } catch (error) {
          item.state = "error";
          item.error = error.message;
          setStatus(error.message, true);
        }
        renderPreviews();
        return;
      }
      start = point;
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
        canvas.setAttribute("aria-label", `Cleaned X-ray view ${index + 1}. Drag to black out anything missed, or click a blackout to remove it.`);
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
      const undo = create("button", "privacy-mini-button", "Remove last blackout");
      undo.type = "button";
      undo.disabled = analysisBusy || item.redactions.length === 0;
      undo.addEventListener("click", async () => {
        if (!item.redactions.length) return;
        item.redactions.pop();
        privacyConfirm.checked = false;
        try {
          await refreshScrubbedFile(item);
          setStatus("Last blackout removed. Check the preview again, then confirm privacy.");
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
      if (!item.sourceCanvas) {
        item.sourceCanvas = await loadImageCanvas(item.file);
        if (item.removed) return;
        revokeUrl(item.originalUrl);
        item.originalUrl = null;
        item.file = null;
      }
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

  const createItem = ({ file = null, sourceCanvas = null, sourceType = "image/png" }) => ({
    id: nextFileId++,
    file,
    sourceType,
    originalUrl: file ? URL.createObjectURL(file) : null,
    scrubbedUrl: null,
    scrubbedFile: null,
    sourceCanvas,
    redactions: [],
    state: "queued",
    error: "",
    removed: false,
  });

  const addFiles = async (incoming) => {
    if (importBusy || analysisBusy) return;
    resetResult();
    privacyConfirm.checked = false;
    importBusy = true;
    updateControls();
    let rejection = "";
    const added = [];
    let omittedFrames = 0;
    let omittedArchiveFiles = 0;
    try {
      const queue = [...incoming];
      while (queue.length) {
        const file = queue.shift();
        if (files.length >= MAX_IMAGES) {
          rejection = "Use no more than four views from one study.";
          break;
        }
        if (isZipCandidate(file)) {
          setStatus("Opening ZIP and converting DICOM image pixels locally…");
          try {
            const { extracted, omitted } = await readZipEntries(file);
            queue.unshift(...extracted);
            omittedArchiveFiles += omitted;
          } catch (error) {
            rejection = error.message || "This ZIP could not be opened.";
          }
          continue;
        }
        if (isDicomCandidate(file)) {
          if (file.size > MAX_DICOM_BYTES) {
            rejection = "Each DICOM file must be 64 MB or smaller.";
            continue;
          }
          setStatus("Converting DICOM image pixels locally…");
          try {
            const remaining = MAX_IMAGES - files.length;
            const { canvases, frameCount } = await loadDicomCanvases(file, remaining);
            canvases.forEach((sourceCanvas) => {
              const item = createItem({ sourceCanvas });
              files.push(item);
              added.push(item);
            });
            omittedFrames += Math.max(0, frameCount - canvases.length);
          } catch (error) {
            rejection = error.message || "This DICOM file could not be decoded.";
          }
          continue;
        }
        if (!supportedTypes.has(file.type)) {
          rejection = "Use DICOM, ZIP, PNG, JPEG or WebP files.";
          continue;
        }
        if (file.size > MAX_BYTES) {
          rejection = "Each screenshot must be 12 MB or smaller.";
          continue;
        }
        const item = createItem({ file, sourceType: file.type });
        files.push(item);
        added.push(item);
      }
    } finally {
      importBusy = false;
      input.value = "";
      folderInput.value = "";
      renderPreviews();
    }
    if (omittedFrames) {
      rejection = `Only the first four views were added; ${omittedFrames} additional DICOM frame${omittedFrames === 1 ? " was" : "s were"} omitted.`;
    } else if (omittedArchiveFiles) {
      rejection = "Only the first four views were added; additional files in the ZIP were omitted.";
    }
    setStatus(
      rejection || (added.length ? "Preparing images and checking visible text locally…" : ""),
      Boolean(rejection && !added.length),
    );
    added.forEach((item) => {
      privacyQueue = privacyQueue.then(() => processItem(item));
    });
  };

  const clearFiles = () => {
    files.forEach(releaseItem);
    files.length = 0;
    input.value = "";
    folderInput.value = "";
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
      rect.setAttribute("stroke-width", supporting ? "4" : "7");
      rect.setAttribute("vector-effect", "non-scaling-stroke");
      if (supporting) {
        rect.setAttribute("class", "supporting-attention-cue");
        rect.setAttribute("stroke-dasharray", "14 10");
        rect.setAttribute("opacity", ".85");
        svg.append(rect);
        return;
      }
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
            `Public-dataset fracture estimate: ${Math.round(model.highest_view_probability * 100)}% on the highest view${model.study_fusion ? " (not separately calibrated across views)" : ""}.`,
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
      } else if (model.kind === "availability") {
        card.append(
          create(
            "p",
            "model-result",
            model.message || "This supporting model is currently offline.",
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
  chooseFolderButton.addEventListener("click", () => folderInput.click());
  clearButton.addEventListener("click", clearFiles);
  analyseButton.addEventListener("click", analyse);
  privacyConfirm.addEventListener("change", updateControls);
  input.addEventListener("change", () => addFiles(input.files));
  folderInput.addEventListener("change", () => addFiles(folderInput.files));
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
  document.addEventListener("paste", (event) => {
    const pasted = [...(event.clipboardData?.files || [])]
      .filter((file) => supportedTypes.has(file.type));
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
