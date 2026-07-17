"""Browser-level coverage for RadSpeed's highest-value web workflows."""
from __future__ import annotations

import re

from playwright.sync_api import Browser, Page, expect


def _console_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


def test_public_impressions_generation_and_validation(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(f"{base_url}/impressions")
    expect(page.get_by_role("heading", name="Findings in. Impression out.")).to_be_visible()

    page.locator("#btn-generate").click()
    expect(page.locator("#status")).to_have_text("Paste some findings first.")

    findings = (
        "CT chest with contrast. There is a 14 mm spiculated right upper lobe "
        "pulmonary nodule. No mediastinal lymphadenopathy or pleural effusion."
    )
    page.locator("#findings").fill(findings)
    page.locator("#modality").fill("CT chest with contrast")
    expect(page.locator("#findings-count")).to_have_text(f"{len(findings)} chars")

    page.locator("#btn-generate").click()
    expect(page.locator("#impression-output")).to_contain_text(
        "No acute cardiopulmonary abnormality", timeout=10_000
    )
    expect(page.locator("#btn-copy")).to_be_enabled()
    expect(page.locator("#status")).to_contain_text("Done")
    assert errors == []


def test_authenticated_transcribe_to_streamed_report(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(base_url)
    expect(page.get_by_role("heading", name="RadSpeed")).to_be_visible()
    expect(page.locator("#template-select option")).not_to_have_count(1)

    page.locator("#template-select").select_option("CT_Chest.txt")
    # Exercise the same browser function used when MediaRecorder finishes.
    # The synthetic blob clears the minimum-size gate; mock mode then returns
    # canned transcription and automatically starts streamed formatting.
    page.evaluate("submitAudioSegment([new Uint8Array(13000)], true)")

    expect(page.locator("#transcription")).to_have_value(
        re.compile("CT chest with contrast"), timeout=10_000
    )
    expect(page.locator("#report-rendered")).to_contain_text(
        "No acute cardiopulmonary abnormality", timeout=15_000
    )
    expect(page.locator("#status")).to_contain_text("Report ready")
    expect(page.locator("#report-status-badge")).to_have_text("Preliminary")
    assert errors == []


def test_mobile_impressions_has_no_horizontal_overflow(page: Page, base_url: str):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{base_url}/impressions")
    expect(page.locator("#findings")).to_be_visible()
    dimensions = page.evaluate(
        "() => ({scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth})"
    )
    assert dimensions["scrollWidth"] <= dimensions["clientWidth"]


def test_main_app_rejects_bad_basic_auth(browser: Browser, base_url: str):
    context = browser.new_context(
        http_credentials={"username": "voxrad", "password": "wrong-password"}
    )
    try:
        response = context.request.get(base_url)
        assert response.status == 401
        assert response.json()["detail"] == "Incorrect password"
    finally:
        context.close()
