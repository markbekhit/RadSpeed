"""Tests for rendering real templates into structured-report prompts."""
import os
import types
import unittest
from unittest.mock import MagicMock, patch

import llm.format as fmt
from config.config import config


def _completion(text):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))]
    )


def _stream_chunk(text):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=text))]
    )


class BundledTemplateTests(unittest.TestCase):
    def test_every_bundled_template_is_nonempty_and_renderable(self):
        names = sorted(
            name for name in os.listdir(fmt._BUNDLED_TEMPLATES_DIR)
            if name.endswith((".txt", ".md"))
        )
        self.assertGreaterEqual(len(names), 40)

        for name in names:
            with self.subTest(template=name):
                content = fmt._get_template_content(name)
                rendered = fmt._template_for_llm(content)
                self.assertTrue(rendered.strip())
                self.assertNotIn(fmt.TEMPLATE_STRUCTURE_MARKER, rendered)
                self.assertNotIn(fmt.TEMPLATE_AI_MARKER, rendered)
                self.assertNotIn("[correct spellings]", rendered.lower())

    def test_user_template_overrides_bundled_template(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "CXR.txt")
            with open(path, "w") as handle:
                handle.write("CUSTOM CXR TEMPLATE")
            with patch.object(fmt, "TEMPLATES_DIR", directory):
                self.assertEqual(fmt._get_template_content("CXR.txt"), "CUSTOM CXR TEMPLATE")

    def test_missing_template_returns_none(self):
        self.assertIsNone(fmt._get_template_content("does-not-exist.txt"))


class StructuredReportRenderingTests(unittest.TestCase):
    def test_rendering_builds_complete_prompt_and_capitalises_labels(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(
            "**FINDINGS:**\nACL: intact\n\n**IMPRESSION:**\nnormal examination"
        )
        template = fmt.join_template(
            "**FINDINGS:**\nACL:\n\n**IMPRESSION:**",
            "Keep the impression concise.\n[correct spellings] ACL [correct spellings]",
        )
        style = {"spelling": "american", "impression_style": "numbered"}

        with patch.object(fmt, "OpenAI", return_value=client):
            report = fmt._create_structured_report(
                "Patient context:\n  Accession: ACC-42\n\nACL is intact", template, style
            )

        self.assertIn("ACL: Intact", report)
        request = client.chat.completions.create.call_args.kwargs
        system_prompt = request["messages"][0]["content"]
        user_prompt = request["messages"][1]["content"]
        self.assertIn("American English", system_prompt)
        self.assertIn("numbered list", system_prompt)
        self.assertIn("Keep the impression concise.", system_prompt)
        self.assertNotIn("correct spellings", system_prompt)
        self.assertNotIn(fmt.TEMPLATE_AI_MARKER, system_prompt)
        self.assertIn("Accession: ACC-42", user_prompt)
        self.assertEqual(request["temperature"], 0.1)

    def test_format_text_passes_patient_context_style_and_selected_template(self):
        old_template = config.global_md_text_content
        old_fhir = getattr(config, "fhir_export_enabled", False)
        config.global_md_text_content = "SELECTED TEMPLATE"
        config.fhir_export_enabled = False
        statuses = []
        style = {"spelling": "british"}
        try:
            with patch.object(fmt, "_create_structured_report", return_value="<think>x</think>REPORT") as create, \
                 patch.object(fmt, "_select_template") as select, \
                 patch.object(fmt, "update_status", statuses.append):
                report = fmt.format_text(
                    "dictated findings",
                    patient_context={"patient_name": "Test Patient", "accession": "ACC-7"},
                    style=style,
                )
        finally:
            config.global_md_text_content = old_template
            config.fhir_export_enabled = old_fhir

        self.assertEqual(report, "REPORT")
        select.assert_not_called()
        transcript, template, passed_style = create.call_args.args
        self.assertIn("Name: Test Patient", transcript)
        self.assertIn("Accession: ACC-7", transcript)
        self.assertTrue(transcript.endswith("dictated findings"))
        self.assertEqual(template, "SELECTED TEMPLATE")
        self.assertIs(passed_style, style)
        self.assertIn("Using user-selected template.", statuses)

    def test_format_text_keyword_selection_uses_bundled_template_without_ai_selection(self):
        old_template = config.global_md_text_content
        old_fhir = getattr(config, "fhir_export_enabled", False)
        config.global_md_text_content = ""
        config.fhir_export_enabled = False
        try:
            with patch.object(fmt, "_select_template") as select, \
                 patch.object(fmt, "_get_template_content", return_value="CXR TEMPLATE") as load, \
                 patch.object(fmt, "_create_structured_report", return_value="CXR REPORT") as create:
                report = fmt.format_text("Portable CXR shows clear lungs")
        finally:
            config.global_md_text_content = old_template
            config.fhir_export_enabled = old_fhir

        self.assertEqual(report, "CXR REPORT")
        select.assert_not_called()
        load.assert_called_once_with("CXR.txt")
        self.assertEqual(create.call_args.args[1], "CXR TEMPLATE")

    def test_stream_rendering_removes_reasoning_blocks(self):
        client = MagicMock()
        client.chat.completions.create.return_value = [
            _stream_chunk("FINDINGS: "),
            _stream_chunk("<think>private reasoning"),
            _stream_chunk(" continues</think>Normal."),
        ]
        with patch.object(fmt, "OpenAI", return_value=client):
            chunks = list(fmt._stream_create_structured_report("dictation", "TEMPLATE"))

        self.assertEqual("".join(chunks), "FINDINGS: Normal.")
        request = client.chat.completions.create.call_args.kwargs
        self.assertTrue(request["stream"])

    def test_stream_format_falls_back_when_no_template_can_be_selected(self):
        with patch.object(fmt, "_keyword_select_template", return_value=None), \
             patch.object(fmt, "_select_template", return_value=None):
            self.assertEqual(
                list(fmt.stream_format_text("unclassified dictation", template_content="")),
                ["Formatted Report:\n\nunclassified dictation"],
            )


if __name__ == "__main__":
    unittest.main()
