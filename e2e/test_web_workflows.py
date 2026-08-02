"""Browser-level coverage for RadSpeed's highest-value web workflows."""
from __future__ import annotations

import io
import re
import time

from PIL import Image, ImageDraw, ImageFont
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


def test_public_landing_page_keeps_impressions_and_sign_in_visible(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(base_url)
    expect(
        page.get_by_role("heading", name="Radiology reporting built around the way you dictate.")
    ).to_be_visible()
    expect(page.get_by_role("link", name="Try Impressions", exact=True).first).to_have_attribute(
        "href", "/impressions"
    )
    expect(page.get_by_role("link", name="Sign in", exact=True).first).to_have_attribute(
        "href", "/app"
    )
    assert errors == []


def test_authenticated_transcribe_to_streamed_report(page: Page, base_url: str):
    errors = _console_errors(page)
    page.goto(f"{base_url}/app")
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


def test_authenticated_fracture_lab_is_reachable_from_radspeed(
    page: Page, base_url: str
):
    errors = _console_errors(page)
    # Production images live on the Fly volume rather than in the repository.
    # Stub image responses here so isolated browser QA can verify the viewer.
    page.route(
        "**/fracture-workbench/images/**",
        lambda route: route.fulfill(
            status=200,
            content_type="image/gif",
            body=(
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
                b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
                b"\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            ),
        ),
    )

    page.goto(f"{base_url}/app")
    expect(page.get_by_role("link", name="Fracture Lab")).to_have_attribute(
        "href", "/fracture-workbench"
    )
    page.get_by_role("link", name="Fracture Lab").click()

    expect(page.get_by_role("heading", name="RadSpeed Fracture Lab")).to_be_visible()
    expect(page.locator(".notice")).to_contain_text("Experimental research interface")
    expect(page.get_by_role("button", name="All 1132")).to_be_visible()
    expect(page.locator("article.card")).to_have_count(1132)
    assert errors == []


def test_fracture_lab_runs_deidentification_engine_entirely_on_site(
    page: Page, base_url: str
):
    errors = _console_errors(page)
    external_requests: list[str] = []
    page.on(
        "request",
        lambda request: external_requests.append(request.url)
        if not request.url.startswith(base_url) and not request.url.startswith("blob:")
        else None,
    )
    page.route(
        "**/fracture-workbench/images/**",
        lambda route: route.fulfill(status=200, content_type="image/gif", body=b"GIF89a"),
    )

    screenshot = Image.new("RGB", (1200, 420), color="black")
    draw = ImageDraw.Draw(screenshot)
    font = ImageFont.load_default(size=58)
    draw.text((35, 35), "PATIENT NAME: EXAMPLE", fill="white", font=font)
    draw.text((35, 125), "MRN: 12345678", fill="white", font=font)
    screenshot_buffer = io.BytesIO()
    screenshot.save(screenshot_buffer, format="PNG")

    page.goto(f"{base_url}/fracture-workbench")
    page.locator("#fracture-file-input").set_input_files(
        {
            "name": "identifiable-synthetic.png",
            "mimeType": "image/png",
            "buffer": screenshot_buffer.getvalue(),
        }
    )

    expect(page.locator(".fracture-preview.privacy-ready")).to_have_count(1, timeout=30_000)
    expect(page.locator("#fracture-privacy-summary")).to_contain_text(
        re.compile(r"[1-9]\d* text areas? covered"), timeout=30_000
    )
    expect(page.locator("#fracture-analyse")).to_be_disabled()
    assert external_requests == []
    assert errors == []


def test_fracture_lab_analyses_uploaded_multiview_study(page: Page, base_url: str):
    errors = _console_errors(page)
    uploaded_payloads: list[bytes] = []

    page.route(
        "**/static/vendor/tesseract/tesseract.min.js*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="""
              window.Tesseract = {
                createWorker: async () => ({
                  recognize: async () => ({ data: { tsv:
                    "level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext\\n" +
                    "5\\t1\\t1\\t1\\t1\\t1\\t8\\t8\\t32\\t12\\t96\\tPATIENT\\n" +
                    "5\\t1\\t1\\t1\\t1\\t2\\t44\\t8\\t36\\t12\\t96\\tNAME\\n" +
                    "5\\t1\\t1\\t1\\t2\\t1\\t80\\t80\\t8\\t8\\t96\\tR"
                  }}),
                  terminate: async () => {},
                }),
              };
            """,
        ),
    )
    page.route(
        "**/fracture-workbench/images/**",
        lambda route: route.fulfill(
            status=200,
            content_type="image/gif",
            body=(
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
                b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
                b"\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            ),
        ),
    )
    synthetic_buffer = io.BytesIO()
    Image.new("L", (96, 96), color=110).save(synthetic_buffer, format="PNG")
    synthetic_xray = synthetic_buffer.getvalue()

    unconfirmed = page.request.post(
        f"{base_url}/api/fracture-analysis",
        multipart={
            "images": {
                "name": "synthetic-view.png",
                "mimeType": "image/png",
                "buffer": synthetic_xray,
            }
        },
    )
    assert unconfirmed.status == 400
    assert "confirm privacy" in unconfirmed.json()["detail"]

    def capture_analysis_request(request):
        if request.url.endswith("/api/fracture-analysis"):
            uploaded_payloads.append(request.post_data_buffer)

    page.on("request", capture_analysis_request)

    page.goto(f"{base_url}/fracture-workbench")
    page.locator("#fracture-file-input").set_input_files(
        [
            {
                "name": "synthetic-view.png",
                "mimeType": "image/png",
                "buffer": synthetic_xray,
            }
        ]
    )
    expect(page.locator(".fracture-preview")).to_have_count(1)
    expect(page.locator("#fracture-privacy-summary")).to_contain_text(
        "2 text areas covered", timeout=10_000
    )
    expect(page.locator("#fracture-analyse")).to_be_disabled()

    # The simulated patient-name boxes are blacked out, while the standard
    # right-side marker is intentionally retained.
    pixels = page.locator(".fracture-preview-canvas").evaluate(
        """canvas => ({
          redacted: Array.from(canvas.getContext('2d').getImageData(10, 10, 1, 1).data),
          marker: Array.from(canvas.getContext('2d').getImageData(82, 82, 1, 1).data),
        })"""
    )
    assert pixels["redacted"][:3] == [0, 0, 0]
    assert pixels["marker"][:3] == [110, 110, 110]

    page.locator(".fracture-preview-canvas").scroll_into_view_if_needed()
    canvas_box = page.locator(".fracture-preview-canvas").bounding_box()
    assert canvas_box
    page.mouse.move(canvas_box["x"] + canvas_box["width"] * 0.52, canvas_box["y"] + canvas_box["height"] * 0.52)
    page.mouse.down()
    page.mouse.move(canvas_box["x"] + canvas_box["width"] * 0.70, canvas_box["y"] + canvas_box["height"] * 0.70)
    page.mouse.up()
    expect(page.locator("#fracture-privacy-summary")).to_contain_text("3 text areas covered")
    assert page.locator(".fracture-preview-canvas").evaluate(
        "canvas => Array.from(canvas.getContext('2d').getImageData(56, 56, 1, 1).data).slice(0, 3)"
    ) == [0, 0, 0]
    page.get_by_role("button", name="Undo blackout").click()
    expect(page.locator("#fracture-privacy-summary")).to_contain_text("2 text areas covered")

    page.locator("#fracture-privacy-confirm").check()
    expect(page.locator("#fracture-analyse")).to_be_enabled()
    page.locator("#fracture-study-type").select_option("chest_ribs")
    page.locator("#fracture-context").fill("Synthetic test context")
    page.locator("#fracture-analyse").click()

    expect(page.locator("#fracture-result")).to_be_visible(timeout=10_000)
    expect(page.locator("#fracture-result")).to_contain_text("Possible fracture")
    expect(page.locator("#fracture-result")).to_contain_text(
        "Open chest classifier estimated fracture probability"
    )
    expect(page.locator("#fracture-result")).to_contain_text("62% model confidence")
    expect(page.locator("#fracture-result svg rect")).to_have_count(1)
    expect(page.locator("#fracture-status")).to_contain_text("Review complete")
    assert uploaded_payloads
    assert b'deidentified-view-' in uploaded_payloads[-1]
    assert b'synthetic-view.png' not in uploaded_payloads[-1]
    assert b'privacy_confirmed' in uploaded_payloads[-1]
    assert b'chest_ribs' in uploaded_payloads[-1]
    assert errors == []


def test_pasted_worksheet_screenshot_generates_report_in_safe_source_mode(
    page: Page, base_url: str
):
    errors = _console_errors(page)
    format_payloads: list[dict] = []

    def capture_format_request(request):
        if request.url.endswith("/format/stream") and request.post_data_json:
            format_payloads.append(request.post_data_json)

    page.on("request", capture_format_request)
    page.goto(f"{base_url}/app")
    expect(page.locator("#worksheet-drop-zone")).to_contain_text(
        "Paste a worksheet snip here"
    )

    page.evaluate(
        """() => {
          const b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZJfQAAAAASUVORK5CYII=";
          const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
          const file = new File([bytes], "renal-worksheet.png", { type: "image/png" });
          const data = new DataTransfer();
          data.items.add(file);
          document.dispatchEvent(new ClipboardEvent("paste", {
            clipboardData: data,
            bubbles: true,
            cancelable: true,
          }));
        }"""
    )

    expect(page.locator(".worksheet-preview")).to_have_count(1)
    expect(page.locator("#btn-worksheet-generate")).to_be_enabled()
    page.locator("#btn-worksheet-generate").click()

    expect(page.locator("#transcription")).to_have_value(
        re.compile("WORKSHEET SOURCE NOTES.*Left kidney", re.DOTALL),
        timeout=10_000,
    )
    expect(page.locator("#report-rendered")).to_contain_text(
        "No acute cardiopulmonary abnormality", timeout=15_000
    )
    expect(page.locator("#status")).to_contain_text("Report ready")
    expect(page.locator("#template-select")).to_have_value("Ultrasound_Worksheet.txt")
    assert format_payloads and format_payloads[-1]["source_kind"] == "worksheet"
    assert format_payloads[-1]["template_name"] == "Ultrasound_Worksheet.txt"

    # Copy must preserve clinical line structure without exporting the browser's
    # paragraph/list spacing. PowerScribe prefers text/html when both clipboard
    # flavours are present, so assert both representations are compact.
    page.evaluate(
        """() => {
          setReport(
            "ULTRASOUND KIDNEYS\\n\\n" +
            "FINDINGS:\\nLeft kidney measures 10.2 cm.\\n\\n" +
            "CONCLUSION:\\n1. No hydronephrosis.\\n2. Simple renal cyst."
          );
          setUI("done");
          document.body.dataset.pasteFormat = "rich";
          window.__worksheetClipboard = {};
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {
              write: async (items) => {
                for (const type of items[0].types) {
                  window.__worksheetClipboard[type] =
                    await (await items[0].getType(type)).text();
                }
              },
            },
          });
        }"""
    )
    page.locator("#btn-copy").click()
    page.wait_for_function(
        "() => Boolean(window.__worksheetClipboard['text/plain'])"
    )
    clipboard = page.evaluate("window.__worksheetClipboard")
    assert clipboard["text/plain"] == (
        "ULTRASOUND KIDNEYS\n\n"
        "FINDINGS:\nLeft kidney measures 10.2 cm.\n\n"
        "CONCLUSION:\n\n"
        "1. No hydronephrosis.\n2. Simple renal cyst."
    )
    assert "<p" not in clipboard["text/html"].lower()
    assert "<li" not in clipboard["text/html"].lower()
    assert "<br>" in clipboard["text/html"].lower()
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
    page.goto(f"{base_url}/app")

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
    page.goto(f"{base_url}/app")
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
    page.goto(f"{base_url}/app")
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
    page.goto(f"{base_url}/app")
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


def test_mobile_landing_has_no_horizontal_overflow(page: Page, base_url: str):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(base_url)
    expect(
        page.get_by_role("heading", name="Radiology reporting built around the way you dictate.")
    ).to_be_visible()
    dimensions = page.evaluate(
        "() => ({scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth})"
    )
    assert dimensions["scrollWidth"] <= dimensions["clientWidth"]


def test_main_app_rejects_bad_basic_auth(browser: Browser, base_url: str):
    context = browser.new_context(
        http_credentials={"username": "voxrad", "password": "wrong-password"}
    )
    try:
        response = context.request.get(f"{base_url}/app")
        assert response.status == 401
        assert response.json()["detail"] == "Incorrect password"
    finally:
        context.close()
