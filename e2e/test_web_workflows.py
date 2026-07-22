"""Browser-level coverage for RadSpeed's highest-value web workflows."""
from __future__ import annotations

import re
import time

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


def test_keyboard_first_reporting_loop_and_automatic_qa(page: Page, base_url: str):
    errors = _console_errors(page)
    qa_requests: list[str] = []
    page.on(
        "request",
        lambda request: qa_requests.append(request.url)
        if request.url.endswith("/api/qa-check")
        else None,
    )
    page.goto(base_url)

    expect(page.locator(".shortcut-strip")).to_contain_text("Ctrl/Cmd+Enter")
    page.locator("#transcription").fill(
        "CT chest with contrast. No focal pulmonary lesion or pleural effusion."
    )
    expect(page.locator("#btn-format")).to_be_enabled()
    page.keyboard.press("Control+Enter")
    expect(page.locator("#report-rendered")).to_contain_text(
        "No acute cardiopulmonary abnormality", timeout=15_000
    )
    page.wait_for_function("() => window.performance.now() > 0 && document.querySelector('#status').textContent !== 'Generating report…'")
    page.wait_for_timeout(200)
    assert qa_requests, "report generation should trigger deterministic QA automatically"

    page.evaluate(
        """() => {
          document.body.dataset.pasteFormat = "plain";
          window.__copiedReport = "";
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: { writeText: async (text) => { window.__copiedReport = text; } },
          });
        }"""
    )
    page.keyboard.press("Control+Shift+C")
    page.wait_for_function("() => window.__copiedReport.includes('No acute cardiopulmonary abnormality')")
    expect(page.locator("#status")).to_contain_text("Report copied")
    assert errors == []


def test_qa_infers_laterality_from_body_part(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(base_url)
    page.locator("#body-part").fill("Right knee")
    page.evaluate(
        """() => {
          setReport("**Findings:**\\nThe left meniscus is intact.");
          setUI("done");
        }"""
    )
    page.locator("#btn-qa").click()
    expect(page.locator("#qa-panel")).to_contain_text(
        "Order is for the RIGHT side", timeout=5_000
    )
    assert errors == []


def test_worklist_switch_replaces_the_whole_case(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(base_url)
    response = page.request.post(
        f"{base_url}/api/worklist/push",
        headers={"X-VoxRad-Agent-Token": "synthetic-mwl-test-token"},
        data={
            "orders": [
                {
                    "patient_name": "Alice Example",
                    "patient_dob": "19600101",
                    "patient_id": "MRN-A",
                    "accession": "ACC-A",
                    "modality": "MR",
                    "body_part": "Left knee",
                },
                {
                    "patient_name": "Bob Example",
                    "patient_dob": "19700202",
                    "patient_id": "MRN-B",
                    "accession": "ACC-B",
                    "modality": "CT",
                    "body_part": "Chest",
                },
            ]
        },
    )
    assert response.ok
    assert response.json()["written"] == 2
    # The file-drop scanner deliberately ignores files still being written.
    time.sleep(1.1)
    page.locator("#btn-worklist-refresh").click()
    expect(page.locator("#worklist-select option")).to_have_count(3)

    page.locator("#worklist-select").select_option("mwl_ACC-A")
    expect(page.locator("#patient-name")).to_have_value("Alice Example")
    expect(page.locator("#body-part")).to_have_value("Left knee")
    expect(page.locator("#patient-summary")).to_contain_text("Alice Example")
    expect(page.locator("#patient-context-details")).not_to_have_attribute("open", "")

    page.locator("#transcription").fill("Unfinished dictation")
    page.locator("#patient-context-details > summary").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("#worklist-select").select_option("mwl_ACC-B")
    expect(page.locator("#worklist-select")).to_have_value("mwl_ACC-A")
    expect(page.locator("#patient-name")).to_have_value("Alice Example")
    expect(page.locator("#transcription")).to_have_value("Unfinished dictation")
    page.locator("#transcription").fill("")

    # A copied/signed case is safe to advance. Switching should clear its text
    # and replace every patient field, never preserve Alice's populated values.
    page.evaluate(
        """() => {
          setReport("**Impression:**\\nNo acute abnormality.");
          setUI("done");
          state.reportCopied = true;
        }"""
    )
    page.locator("#worklist-select").select_option("mwl_ACC-B")
    expect(page.locator("#patient-name")).to_have_value("Bob Example")
    expect(page.locator("#patient-id")).to_have_value("MRN-B")
    expect(page.locator("#accession")).to_have_value("ACC-B")
    expect(page.locator("#body-part")).to_have_value("Chest")
    expect(page.locator("#report-raw")).to_have_value("")
    expect(page.locator("#transcription")).to_have_value("")
    assert errors == []


def test_followup_prompt_and_manual_score_insertion(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(base_url)
    page.evaluate(
        """() => {
          setReport("**IMPRESSION:**\\nIndeterminate pulmonary nodule. Follow-up CT chest in 12 months is recommended.");
          setUI("done");
        }"""
    )
    expect(page.locator("#followup-suggest-panel")).to_contain_text(
        "Follow-up CT chest in 12 months", timeout=5_000
    )
    expect(page.locator("#followup-suggest-panel").get_by_role("button", name="Track")).to_be_visible()

    page.locator("#btn-scores").click()
    page.locator("#score-system").select_option("ACR TI-RADS")
    page.locator("#score-category").select_option("TR5")
    page.locator("#score-target").fill("Right thyroid nodule")
    expect(page.locator("#score-preview")).to_contain_text("TR5 — Highly suspicious")
    page.locator("#score-insert").click()
    expect(page.locator("#report-raw")).to_have_value(
        re.compile(r"Right thyroid nodule: TR5 — Highly suspicious")
    )
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
