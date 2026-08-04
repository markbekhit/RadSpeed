"""Regression coverage for Fracture Lab image paste behaviour."""
from __future__ import annotations

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


def test_fracture_lab_accepts_image_paste_without_drop_zone_focus(
    page: Page, base_url: str
):
    page.goto(f"{base_url}/fracture-workbench")
    expect(page.locator("#fracture-drop-zone")).not_to_be_focused()

    _paste_png_on_document(page)

    expect(page.locator(".fracture-preview")).to_have_count(1)
