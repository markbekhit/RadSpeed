"""Regression coverage for private, browser-only Fracture Lab DICOM import."""
from __future__ import annotations

import json
import struct

from playwright.sync_api import Page, expect


def _element(group: int, element: int, vr: str, value: bytes) -> bytes:
    if len(value) % 2:
        value += b"\x00" if vr == "UI" else b" "
    tag = struct.pack("<HH", group, element)
    if vr in {"OB", "OW", "SQ", "UN", "UT"}:
        return tag + vr.encode() + b"\x00\x00" + struct.pack("<I", len(value)) + value
    return tag + vr.encode() + struct.pack("<H", len(value)) + value


def _synthetic_multiframe_dicom() -> bytes:
    sop_class = b"1.2.840.10008.5.1.4.1.1.1.1"
    sop_instance = b"1.2.826.0.1.3680043.10.999.1"
    meta_body = b"".join(
        [
            _element(0x0002, 0x0001, "OB", b"\x00\x01"),
            _element(0x0002, 0x0002, "UI", sop_class),
            _element(0x0002, 0x0003, "UI", sop_instance),
            _element(0x0002, 0x0010, "UI", b"1.2.840.10008.1.2.1"),
            _element(0x0002, 0x0012, "UI", b"1.2.826.0.1.3680043.10.999"),
        ]
    )
    meta = _element(0x0002, 0x0000, "UL", struct.pack("<I", len(meta_body))) + meta_body

    width = height = 96
    first = bytes((x * 255 // (width - 1)) for _y in range(height) for x in range(width))
    second = bytes(255 - value for value in first)
    dataset = b"".join(
        [
            _element(0x0008, 0x0016, "UI", sop_class),
            _element(0x0008, 0x0018, "UI", sop_instance),
            _element(0x0010, 0x0010, "PN", b"SYNTHETIC^PATIENT"),
            _element(0x0010, 0x0020, "LO", b"SYNTHETIC-MRN-123"),
            _element(0x0028, 0x0002, "US", struct.pack("<H", 1)),
            _element(0x0028, 0x0004, "CS", b"MONOCHROME2"),
            _element(0x0028, 0x0008, "IS", b"2"),
            _element(0x0028, 0x0010, "US", struct.pack("<H", height)),
            _element(0x0028, 0x0011, "US", struct.pack("<H", width)),
            _element(0x0028, 0x0100, "US", struct.pack("<H", 8)),
            _element(0x0028, 0x0101, "US", struct.pack("<H", 8)),
            _element(0x0028, 0x0102, "US", struct.pack("<H", 7)),
            _element(0x0028, 0x0103, "US", struct.pack("<H", 0)),
            _element(0x0028, 0x1050, "DS", b"127.5"),
            _element(0x0028, 0x1051, "DS", b"256"),
            _element(0x7FE0, 0x0010, "OB", first + second),
        ]
    )
    return bytes(128) + b"DICM" + meta + dataset


def test_dicom_is_rasterised_locally_before_upload(page: Page, base_url: str):
    errors: list[str] = []
    uploaded_payloads: list[bytes] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: uploaded_payloads.append(request.post_data_buffer)
        if request.url.endswith("/api/fracture-analysis")
        else None,
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
            "assessment": "indeterminate",
            "confidence_percent": 50,
            "summary": "Synthetic assessment.",
            "key_findings": [],
            "limitations": ["Synthetic test."],
            "views": [
                {"view_index": 1, "summary": "First frame.", "confidence_percent": 50, "boxes": []},
                {"view_index": 2, "summary": "Second frame.", "confidence_percent": 50, "boxes": []},
            ],
        },
        "supporting_models": [],
    }
    page.route(
        "**/api/fracture-analysis",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(response)
        ),
    )

    page.goto(f"{base_url}/fracture-workbench")
    expect(page.locator("#fracture-drop-zone")).to_contain_text("DICOM")
    page.locator("#fracture-file-input").set_input_files(
        {
            "name": "named-patient-study.dcm",
            "mimeType": "application/dicom",
            "buffer": _synthetic_multiframe_dicom(),
        }
    )
    expect(page.locator(".fracture-preview.privacy-ready")).to_have_count(2, timeout=30_000)
    first_frame = page.locator(".fracture-preview-canvas").first.evaluate(
        "canvas => Array.from(canvas.getContext('2d').getImageData(12, 48, 1, 1).data).slice(0, 3)"
    )
    second_frame = page.locator(".fracture-preview-canvas").nth(1).evaluate(
        "canvas => Array.from(canvas.getContext('2d').getImageData(12, 48, 1, 1).data).slice(0, 3)"
    )
    assert first_frame[0] < second_frame[0]

    page.locator("#fracture-privacy-confirm").check()
    page.locator("#fracture-analyse").click()
    expect(page.locator("#fracture-result")).to_be_visible(timeout=10_000)

    assert uploaded_payloads
    payload = uploaded_payloads[-1]
    assert payload.count(b"deidentified-view-") == 2
    assert b"named-patient-study.dcm" not in payload
    assert b"SYNTHETIC^PATIENT" not in payload
    assert b"SYNTHETIC-MRN-123" not in payload
    assert b"DICM" not in payload
    assert errors == []
