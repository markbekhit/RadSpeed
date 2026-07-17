"""Regression tests for the synthetic clinical quality evaluator."""
import unittest

from evals.clinical_quality import evaluate_case, evaluate_suite, load_cases


class ClinicalQualityEvaluatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()

    def test_curated_reference_suite_passes(self):
        reports = {case["id"]: case["reference_report"] for case in self.cases}
        results = evaluate_suite(self.cases, reports)
        self.assertGreaterEqual(len(results), 6)
        self.assertTrue(all(result.passed for result in results))

    def test_wrong_laterality_and_missing_measurement_fail(self):
        case = next(case for case in self.cases if case["id"] == "mri_brain_left_infarct")
        report = (
            "FINDINGS: Small acute infarct in the right thalamus with diffusion restriction. "
            "No haemorrhagic transformation. IMPRESSION: Acute right thalamic infarct."
        )
        result = evaluate_case(case, report)
        self.assertFalse(result.passed)
        failed = {check.name for check in result.checks if not check.passed}
        self.assertIn("laterality:left", failed)
        self.assertIn("measurement:8 mm", failed)

    def test_contradictory_forbidden_statement_fails(self):
        case = next(case for case in self.cases if case["id"] == "ctpa_right_lower_lobe_embolus")
        report = case["reference_report"] + "\nNo pulmonary embolus."
        result = evaluate_case(case, report)
        self.assertFalse(result.passed)
        self.assertIn(
            "forbidden:no pulmonary embolus",
            {check.name for check in result.checks if not check.passed},
        )

    def test_reversed_section_order_fails_structure_check(self):
        case = next(case for case in self.cases if case["id"] == "ct_head_negative")
        report = "IMPRESSION: No acute intracranial abnormality. FINDINGS: No acute intracranial haemorrhage. No calvarial fracture."
        result = evaluate_case(case, report)
        self.assertFalse(next(check.passed for check in result.checks if check.name == "section_order"))

    def test_common_intact_ligament_punctuation_is_accepted(self):
        case = next(case for case in self.cases if case["id"] == "mri_knee_medial_meniscus")
        report = case["reference_report"].replace("ACL and PCL are intact", "ACL and PCL: Intact")
        self.assertTrue(evaluate_case(case, report).passed)


if __name__ == "__main__":
    unittest.main()
