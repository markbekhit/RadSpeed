"""Regression coverage for Fracture Lab result overlays."""
from __future__ import annotations

import json

from playwright.sync_api import Page, expect

_SYNTHETIC_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAAAAADH8yjkAAAAX0lEQVR4nO3QsQ0A"
    "MAzDsLQH9/+xJ2jKRh5gAzpvdt3l/XGQJEoSJYmSREmiJFGSKEmUJEoSJYmSREmi"
    "JFGSKEmUJEoSJYmSREmiJFGSKEmUJEoSJYmSREmiJFFaT/QBauUBLoh6PMIAAAAA"
    "SUVORK5CYII="
)


def _paste_png_on_document(page: Page) -> None:
    page.evaluate(
        """(b64) => {
          const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
          const file = new File([bytes], "synthetic-xray.png", { type: "image/png" });
          const data = new DataTransfer();
          data.items.add(file);
          document.dispatchEvent(new ClipboardEvent("paste", {
            clipboardData: data,
            bubbles: true,
            cancelable: true,
          }));
        }""",
        _SYNTHETIC_PNG,
    )


def test_supporting_attention_boxes_do_not_cover_images_with_text(
    page: Page, base_url: str
):
    page.route(
        "**/static/vendor/tesseract/tesseract.min.js*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="""
              window.Tesseract = {
                createWorker: async () => ({
                  recognize: async () => ({ data: { tsv:
                    "level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n"
                  }}),
                  terminate: async () => {},
                }),
              };
            """,
        ),
    )
    response = {
        "assessment": {
            "study_region": "other",
            "assessment": "possible_fracture",
            "confidence_percent": 62,
            "summary": "Synthetic assessment.",
            "key_findings": ["Synthetic finding."],
            "limitations": ["Synthetic limitation."],
            "views": [
                {
                    "view_index": 1,
                    "summary": "Synthetic view.",
                    "confidence_percent": 58,
                    "boxes": [],
                }
            ],
        },
        "supporting_models": [
            {
                "kind": "locator",
                "label": "Open broad fracture locator",
                "scope": "General extremity radiographs",
                "views": [
                    {
                        "view_index": 1,
                        "boxes": [
                            {
                                "x_min": 240,
                                "y_min": 260,
                                "x_max": 520,
                                "y_max": 560,
                                "label": "attention cue",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    page.route(
        "**/api/fracture-analysis",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(response),
        ),
    )

    page.goto(f"{base_url}/fracture-workbench")
    _paste_png_on_document(page)
    expect(page.locator(".fracture-preview.privacy-ready")).to_have_count(
        1, timeout=10_000
    )
    page.locator("#fracture-privacy-confirm").check()
    page.locator("#fracture-analyse").click()

    cue = page.locator("#fracture-result svg .supporting-attention-cue")
    expect(cue).to_have_count(1)
    expect(cue).to_have_attribute("stroke-width", "4")
    expect(page.locator("#fracture-result svg text")).to_have_count(0)
