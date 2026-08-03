"""Adapt the offline benchmark review into RadSpeed's authenticated viewer."""

from __future__ import annotations

import argparse
from pathlib import Path


SOURCE_IMAGE_PREFIX = "../../data/extracted/orthofrac_xr/OrthoFrac-XR/"
HOSTED_IMAGE_PREFIX = "/fracture-workbench/images/"


def build(source: Path, destination: Path) -> int:
    html = source.read_text(encoding="utf-8")
    image_count = html.count(SOURCE_IMAGE_PREFIX)
    if image_count == 0:
        raise ValueError("No OrthoFrac-XR image references were found")

    html = html.replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <meta name="robots" content="noindex, nofollow">',
    )
    html = html.replace(
        "<title>Hybrid fracture model review</title>",
        "<title>Fracture Lab · RadSpeed</title>\n"
        '  <link rel="stylesheet" href="/static/fracture-lab.css?v=independent-models-1">',
    )
    html = html.replace(
        "    .notice { max-width: 900px; color: #fbbf24; }",
        "    .notice { max-width: 1050px; color: #fbbf24; }\n"
        "    .back { color: #93c5fd; text-decoration: none; }\n"
        "    .back:hover { text-decoration: underline; }",
    )
    html = html.replace(
        "  <h1>Hybrid fracture model review</h1>",
        '  <p><a class="back" href="/app">← Back to RadSpeed</a></p>\n'
        "  <h1>RadSpeed Fracture Lab</h1>",
    )
    html = html.replace(
        '<p class="notice">Public research images only.',
        '<p class="notice"><strong>Experimental research interface.</strong> '
        "The benchmark below uses public research images only. ",
    )
    notice_end = (
        "All boxes are approximate research proposals, not validated localisations. "
        "Not for patient care.</p>"
    )
    attribution = (
        notice_end
        + '\n  <p>Images: <a class="back" '
        + 'href="https://doi.org/10.6084/m9.figshare.32021085.v1" '
        + 'rel="external noopener">OrthoFrac-XR v1</a> by Tabib, Liza, Bijoy, '
        + 'Hasan and Khan, <a class="back" '
        + 'href="https://creativecommons.org/licenses/by/4.0/" '
        + 'rel="external noopener">CC BY 4.0</a>.</p>'
    )
    if notice_end not in html:
        raise ValueError("The benchmark safety notice could not be found")
    html = html.replace(notice_end, attribution, 1)
    analysis_panel = """\
  <section class="analysis-panel" aria-labelledby="live-analysis-heading">
    <div class="analysis-heading">
      <div>
        <div class="eyebrow">Private experimental second read</div>
        <h2 id="live-analysis-heading">Analyse your X-rays</h2>
      </div>
      <span class="privacy-pill">Not saved by RadSpeed</span>
    </div>
    <p class="analysis-intro">Add up to four views from one study. RadSpeed identifies the anatomy automatically. Before upload, your browser checks for visible text and blacks it out locally. The cleaned copies receive one frontier-model read and a separate check from the relevant open model; the opinions are shown independently.</p>
    <div id="fracture-drop-zone" class="fracture-drop-zone" tabindex="0" role="button" aria-label="Choose, paste or drop X-ray images">
      <strong>Paste, drop or choose X-ray screenshots</strong>
      <span>PNG, JPEG or WebP · up to 4 views · 12 MB each</span>
    </div>
    <input id="fracture-file-input" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden>
    <div id="fracture-preview-list" class="fracture-preview-list" aria-live="polite"></div>
    <section id="fracture-privacy-panel" class="privacy-review" aria-labelledby="fracture-privacy-heading" hidden>
      <div>
        <strong id="fracture-privacy-heading">Privacy check before upload</strong>
        <p id="fracture-privacy-summary"></p>
        <p class="privacy-instruction">The previews above are the copies that will be analysed. Drag over anything missed to add a permanent black box. Laterality and standard view markers are kept where recognised.</p>
      </div>
      <label class="privacy-confirmation">
        <input id="fracture-privacy-confirm" type="checkbox">
        <span>I checked the cleaned previews and no patient details remain.</span>
      </label>
    </section>
    <label class="context-label" for="fracture-context">Optional clinical context <span>(no patient identifiers)</span></label>
    <input id="fracture-context" class="context-input" type="text" maxlength="500" placeholder="e.g. FOOSH, focal radial styloid tenderness">
    <div class="analysis-actions">
      <button id="fracture-choose" type="button">Choose images</button>
      <button id="fracture-clear" type="button" disabled>Clear</button>
      <button id="fracture-analyse" class="primary-action" type="button" disabled>Analyse study</button>
    </div>
    <p class="privacy-copy">Visible-text checking and blackouts happen in this browser. The unredacted screenshot is not uploaded. The cleaned copy is also stripped of hidden metadata by RadSpeed, processed ephemerally by RadSpeed's configured vision-model provider, and not retained by RadSpeed. Automated de-identification can miss text, so the preview check remains required. This is unofficial decision support and must not replace your interpretation.</p>
    <div id="fracture-status" class="fracture-status" role="status" aria-live="polite"></div>
    <section id="fracture-result" class="fracture-result" aria-live="polite" hidden></section>
  </section>
  <div class="benchmark-heading">
    <div class="eyebrow">Retrospective validation</div>
    <h2>Public benchmark cases</h2>
  </div>
"""
    html = html.replace("  <nav>\n", analysis_panel + "  <nav>\n", 1)
    html = html.replace(SOURCE_IMAGE_PREFIX, HOSTED_IMAGE_PREFIX)
    html = html.replace(
        "</body>",
        '  <script src="/static/vendor/tesseract/tesseract.min.js?v=7.0.0"></script>\n'
        '  <script src="/static/fracture-lab.js?v=independent-models-1"></script>\n</body>',
        1,
    )

    if html.count(HOSTED_IMAGE_PREFIX) != image_count:
        raise ValueError("Not all image references were converted")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return image_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = build(args.source, args.destination)
    print(f"Built {args.destination} with {count} image references")


if __name__ == "__main__":
    main()
