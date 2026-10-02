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

    # Value: protects=ambiguous worksheet labels do not create polarity alerts;
    # fails_when=short unstructured form labels are treated as asserted findings;
    # why_new=dictation polarity tests do not cover worksheet extraction noise;
    # seam=none
    def test_ignores_ambiguous_worksheet_labels_covered_by_negative_report(self):
        source = (
            "FORM EXTRACT — blank fields are unknown:\n"
            "Free fluid collection seen\n"
            "Adnexal mass seen bilaterally"
        )
        report = (
            "No evidence of focal lesion, hyperaemia or free fluid collection. "
            "No free fluid seen in either iliac fossa.\n"
            "No evidence of ovarian or adnexal mass bilaterally."
        )

        self.assertEqual(
            check_source_omissions(report, source, source_kind="worksheet"),
            [],
        )
        self.assertEqual(
            check_source_omissions(
                "No mass is identified.",
                "Mass seen",
                source_kind="worksheet",
            ),
            [],
        )
        self.assertEqual(
            check_source_omissions(
                "No renal mass. No adnexal mass.",
                "Renal mass: absent\nAdnexal mass seen",
                source_kind="worksheet",
            ),
            [],
        )
        self.assertEqual(
            len(check_source_omissions(
                "No abdominal free fluid collection.",
                "Pelvic free fluid collection seen",
                source_kind="worksheet",
            )),
            1,
        )
        for narrower_report in (
            "No left adnexal mass.",
            "No new adnexal mass.",
            "No free fluid collection in the right iliac fossa.",
            "No suspicious adnexal mass.",
            "No free fluid collection in the pelvis.",
            "No large free fluid collection.",
            "No residual free fluid collection.",
            "No free fluid collection, right iliac fossa.",
        ):
            source_label = (
                "Free fluid collection seen"
                if "fluid" in narrower_report
                else "Adnexal mass seen"
            )
            with self.subTest(narrower_report=narrower_report):
                self.assertEqual(
                    len(check_source_omissions(
                        narrower_report,
                        source_label,
                        source_kind="worksheet",
                    )),
                    1,
                )
        for source_label, different_location_report in (
            ("RUL nodule seen", "No LUL nodule."),
            ("Segment 7 lesion seen", "No segment 8 lesion."),
        ):
            with self.subTest(different_location_report=different_location_report):
                self.assertEqual(
                    len(check_source_omissions(
                        different_location_report,
                        source_label,
                        source_kind="worksheet",
                    )),
                    1,
                )

    # Value: protects=worksheet noise is suppressed only when a negative report covers it;
    # fails_when=the worksheet exception hides omitted or explicitly positive findings;
    # why_new=the false-positive regression covers only matched negative report clauses;
    # seam=none
    def test_keeps_polarity_alert_for_dictation_and_structured_worksheet_values(self):
        report = "No free fluid collection. No adnexal mass bilaterally."
        self.assertEqual(
            len(check_source_omissions(
                report,
                "Free fluid collection seen. Adnexal mass seen bilaterally.",
            )),
            2,
        )
        self.assertEqual(
            len(check_source_omissions(
                "The appendix is normal.",
                "WORKSHEET SOURCE NOTES — blank/unmarked fields are unknown:\n"
                "Free fluid collection seen",
                source_kind="worksheet",
            )),
            1,
        )
        for structured_value in (
            "Free fluid collection abnormal",
            "Free fluid collection definite",
            "Free fluid collection positive",
            "Free fluid collection present",
            "Free fluid collection yes",
            "Free fluid collection seen measuring 5 mm",
            "☑ Free fluid collection seen",
            "[x] Free fluid collection seen",
            "(x) Free fluid collection seen",
            "● Free fluid collection seen",
            "■ Free fluid collection seen",
            "Free fluid = collection seen",
            "Free fluid — collection seen",
            "☑ Free fluid or collection seen",
            "Pelvis / free fluid: none, but collection seen",
        ):
            with self.subTest(structured_value=structured_value):
                self.assertEqual(
                    len(check_source_omissions(
                        report,
                        "WORKSHEET SOURCE NOTES — blank/unmarked fields are unknown:\n"
                        + structured_value,
                        source_kind="worksheet",
                    )),
                    1,
                )
        self.assertEqual(
            len(check_source_omissions(
                report,
                "WORKSHEET SOURCE NOTES — blank/unmarked fields are unknown:\n"
                "Pelvis / free fluid: Collection seen\n"
                "Adnexa / bilateral: Mass seen",
                source_kind="worksheet",
            )),
            2,
        )

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

    def test_but_boundary_keeps_each_findings_polarity(self):
        self.assertEqual(
            len(check_source_omissions(
                "No free fluid, but a left adnexal mass is present.",
                "No adnexal mass.",
            )),
            1,
        )

    def test_no_interval_change_means_stable_not_absent(self):
        self.assertEqual(check_source_omissions(
            "No interval change in the right renal mass.",
            "Unchanged right renal mass.",
        ), [])
        self.assertEqual(check_source_omissions(
            "No significant change in pulmonary nodule.",
            "Stable pulmonary nodule.",
        ), [])
        self.assertEqual(check_source_omissions(
            "No interval change in the right renal mass or adrenal nodule.",
            "Stable adrenal nodule.",
        ), [])
        self.assertTrue(check_source_omissions(
            "No acute abnormality.",
            "No interval change in size or appearance of the left adrenal nodule.",
        ))
        self.assertTrue(check_source_omissions(
            "No acute abnormality.",
            "No interval worsening in size or appearance of the left adrenal nodule.",
        ))

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
