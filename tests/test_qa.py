"""Deterministic report QA checks."""

import unittest

from web.qa import check_source_omissions, run_qa_checks


class SourceOmissionTests(unittest.TestCase):
    def test_flags_a_separately_dictated_plc_injury_missing_from_report(self):
        source = (
            "There is a full thickness tear of the proximal popliteus tendon "
            "and complete rupture of the arcuate ligament."
        )
        report = "Full-thickness tear of the proximal popliteus tendon."

        flags = check_source_omissions(report, source)

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["type"], "source_omission")
        self.assertIn("arcuate ligament", flags[0]["location"])

    def test_accepts_common_paraphrase_of_dictated_injury(self):
        source = "There is complete rupture of the lateral collateral ligament."
        report = "The fibular collateral ligament is completely torn."

        self.assertEqual(check_source_omissions(report, source), [])

    def test_ignores_normal_negative_clause(self):
        source = "No joint effusion. The menisci are intact."
        report = "Both menisci are intact."

        self.assertEqual(check_source_omissions(report, source), [])

    def test_flags_reversed_pathology_polarity(self):
        self.assertTrue(check_source_omissions("No acute fracture.", "Acute fracture."))
        self.assertTrue(check_source_omissions("Acute fracture.", "No acute fracture."))

    def test_flags_one_reversed_finding_from_compound_negative(self):
        source = "No acute fracture or dislocation."
        self.assertTrue(check_source_omissions("Acute dislocation.", source))
        self.assertTrue(check_source_omissions("Acute fracture.", source))

    def test_anatomy_only_overlap_does_not_hide_pathology_omission(self):
        self.assertTrue(check_source_omissions(
            "The ACL is completely obscured by artifact.",
            "Complete tear of the ACL.",
        ))

    def test_matching_polarity_wins_when_report_mentions_both_states(self):
        self.assertEqual(check_source_omissions(
            "No acute fracture. Chronic fracture deformity.",
            "No acute fracture.",
        ), [])

    def test_no_interval_change_means_stable_not_absent(self):
        self.assertEqual(check_source_omissions(
            "No interval change in the right renal mass.",
            "Unchanged right renal mass.",
        ), [])
        self.assertEqual(check_source_omissions(
            "No significant change in pulmonary nodule.",
            "Stable pulmonary nodule.",
        ), [])

    def test_identical_short_pathology_does_not_warn(self):
        self.assertEqual(check_source_omissions("Mass.", "Mass."), [])
        self.assertEqual(check_source_omissions("5 mm mass.", "5 mm mass."), [])

    def test_flags_compound_finding_joined_by_with(self):
        source = (
            "Complete rupture of the arcuate ligament with a full-thickness "
            "popliteus tendon tear."
        )
        report = "Complete tear of the arcuate ligament."

        flags = check_source_omissions(report, source)
        self.assertEqual(len(flags), 1)
        self.assertIn("popliteus tendon", flags[0]["location"])

    def test_flags_opposite_pathology_and_changed_measurement(self):
        self.assertTrue(check_source_omissions(
            "The anterior cruciate ligament is intact.",
            "Complete ACL tear.",
        ))
        self.assertTrue(check_source_omissions(
            "A 7 mm pulmonary nodule is present.",
            "A 5 mm pulmonary nodule is present.",
        ))

    def test_accepts_equivalent_measurement_units(self):
        self.assertEqual(check_source_omissions(
            "A 0.5 cm pulmonary nodule is present.",
            "A 5 mm pulmonary nodule is present.",
        ), [])

    def test_short_mass_and_multi_structure_tear_remain_covered(self):
        self.assertTrue(check_source_omissions("No focal lesion.", "Mass."))
        self.assertTrue(check_source_omissions(
            "Complete anterior cruciate ligament tear.",
            "Complete ACL tear and meniscal root injury.",
        ))

    def test_public_entry_point_includes_source_coverage(self):
        flags = run_qa_checks(
            report_text="Posterolateral corner injury.",
            source_text="Complete rupture of the arcuate ligament.",
            body_part="knee",
        )

        self.assertIn("source_omission", {flag["type"] for flag in flags})


if __name__ == "__main__":
    unittest.main()
