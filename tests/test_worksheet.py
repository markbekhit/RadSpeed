"""Regression coverage for worksheet screenshot extraction and safe formatting."""

from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm import format as report_format
from llm.worksheet import (
    MAX_WORKSHEET_IMAGE_BYTES,
    WorksheetImageError,
    extract_worksheet_findings,
    validate_worksheet_images,
)
from config.config import config


def _completion(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class WorksheetImageValidationTests(unittest.TestCase):
    def test_detects_supported_images_from_magic_bytes(self):
        images = validate_worksheet_images(
            [
                b"\x89PNG\r\n\x1a\nsynthetic",
                b"\xff\xd8\xffsynthetic",
                b"RIFF\x08\x00\x00\x00WEBPsynthetic",
            ]
        )
        self.assertEqual(
            [image.mime_type for image in images],
            ["image/png", "image/jpeg", "image/webp"],
        )

    def test_rejects_unsupported_or_oversized_payloads(self):
        with self.assertRaisesRegex(WorksheetImageError, "supported PNG"):
            validate_worksheet_images([b"not-an-image"])
        with self.assertRaisesRegex(WorksheetImageError, "8 MB"):
            validate_worksheet_images(
                [b"\x89PNG\r\n\x1a\n" + b"x" * MAX_WORKSHEET_IMAGE_BYTES]
            )


class WorksheetExtractionPromptTests(unittest.TestCase):
    def test_multiple_images_use_high_detail_and_table_safety_rules(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "Right kidney: 10.8 cm.\nLeft kidney: mild pelvicaliectasis."
        )
        images = validate_worksheet_images(
            [
                b"\x89PNG\r\n\x1a\npage-one",
                b"\xff\xd8\xffpage-two",
            ]
        )

        with patch("llm.worksheet.OpenAI", return_value=client):
            findings = extract_worksheet_findings(
                images, modality="US", body_part="Renal tract"
            )

        self.assertIn("Left kidney", findings)
        request = client.chat.completions.create.call_args.kwargs
        system = request["messages"][0]["content"]
        user_content = request["messages"][1]["content"]
        self.assertIn("blank or unmarked field means unknown", system)
        self.assertIn("row", system)
        self.assertIn("column", system)
        self.assertIn("Exclude patient names", system)
        self.assertIn('unchecked option as "not selected"', system)
        self.assertEqual(user_content[1]["image_url"]["detail"], "high")
        self.assertEqual(user_content[2]["image_url"]["detail"], "high")
        self.assertTrue(
            user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        )
        encoded = user_content[1]["image_url"]["url"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), images[0].data)

    def test_no_findings_sentinel_is_preserved(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "NO_EXTRACTABLE_FINDINGS"
        )
        image = validate_worksheet_images([b"\x89PNG\r\n\x1a\nblank"])
        with patch("llm.worksheet.OpenAI", return_value=client):
            self.assertEqual(
                extract_worksheet_findings(image), "NO_EXTRACTABLE_FINDINGS"
            )

    def test_gpt5_worksheet_request_uses_supported_completion_parameters(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "Right kidney: 10.8 cm."
        )
        image = validate_worksheet_images([b"\x89PNG\r\n\x1a\nsynthetic"])

        old_model = config.SELECTED_MODEL
        config.SELECTED_MODEL = "gpt-5.6-sol"
        try:
            with patch("llm.worksheet.OpenAI", return_value=client):
                extract_worksheet_findings(image)
        finally:
            config.SELECTED_MODEL = old_model

        request = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("temperature", request)
        self.assertNotIn("max_tokens", request)
        self.assertEqual(request["max_completion_tokens"], 3000)


class WorksheetFormattingSafetyTests(unittest.TestCase):
    def test_worksheet_mode_overrides_normal_completion(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "**FINDINGS:**\nLeft renal pelvicaliectasis."
        )
        with patch("llm.format.OpenAI", return_value=client):
            report_format._create_structured_report(
                "Left kidney: mild pelvicaliectasis.",
                "**FINDINGS:**\n[documented findings]",
                source_kind="worksheet",
            )

        request = client.chat.completions.create.call_args.kwargs
        system = request["messages"][0]["content"]
        user = request["messages"][1]["content"]
        self.assertIn("supersedes rule 5", system)
        self.assertIn("never normal", system)
        self.assertIn("Do NOT add normal descriptors", system)
        self.assertIn("sonographer worksheet screenshots", user)

    def test_dictation_mode_keeps_existing_completion_behaviour(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "**FINDINGS:**\nNo acute abnormality."
        )
        with patch("llm.format.OpenAI", return_value=client):
            report_format._create_structured_report(
                "No acute abnormality.", "**FINDINGS:**\n[findings]"
            )

        system = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertNotIn("Worksheet-source safety override", system)


if __name__ == "__main__":
    unittest.main()
