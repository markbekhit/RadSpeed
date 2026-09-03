"""Impression-only report integration helpers."""

import unittest

from llm.impressions import (
    _select_relevant_guidelines,
    extract_findings,
    replace_impression,
)


class ReportImpressionHelpersTests(unittest.TestCase):
    def test_thyroid_findings_select_tirads_guidance(self):
        matched = _select_relevant_guidelines(
            "Synthetic thyroid nodules: 26 mm TR2 and 6 mm TR3."
        )
        self.assertEqual(
            [name for name, _content in matched],
            ["ACR TI-RADS (thyroid nodules on US)"],
        )

    def test_extract_findings_stops_at_impression(self):
        report = (
            "**EXAM:**\nThyroid ultrasound.\n\n"
            "**FINDINGS:**\nRight lobe: Normal.\nThyroid nodules: Synthetic TR3 nodule.\n\n"
            "**IMPRESSION:**\n- Old impression."
        )
        self.assertEqual(
            extract_findings(report),
            "Right lobe: Normal.\nThyroid nodules: Synthetic TR3 nodule.",
        )

    def test_replace_impression_preserves_all_other_sections(self):
        report = (
            "**EXAM:**\nThyroid ultrasound.\n\n"
            "**FINDINGS:**\nSynthetic finding.\n\n"
            "**IMPRESSION:**\n- Old impression."
        )
        updated = replace_impression(report, "- New impression.\n- No follow-up required.")
        self.assertIn("**EXAM:**\nThyroid ultrasound.", updated)
        self.assertIn("**FINDINGS:**\nSynthetic finding.", updated)
        self.assertIn("**IMPRESSION:**\n\n- New impression.", updated)
        self.assertNotIn("Old impression", updated)

    def test_replace_impression_adds_missing_section(self):
        report = "**FINDINGS:**\nSynthetic finding."
        self.assertEqual(
            replace_impression(report, "- New impression."),
            "**FINDINGS:**\nSynthetic finding.\n\n**IMPRESSION:**\n\n- New impression.",
        )


if __name__ == "__main__":
    unittest.main()
