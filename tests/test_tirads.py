"""ACR TI-RADS calculator: scoring module, API and public page."""

import unittest

from fastapi.testclient import TestClient

from web import tirads
from web.app import app


class TiradsScoringTests(unittest.TestCase):
    def test_lowest_score_is_tr1_no_action(self):
        r = tirads.score("cystic", "anechoic", "wider", "smooth", foci=["none"])
        self.assertEqual(r["points"], 0)
        self.assertEqual(r["level"], "TR1")
        self.assertIsNone(r["fna_threshold_cm"])
        self.assertIn("No FNA", r["management"])

    def test_level_band_boundaries(self):
        # Points -> level: 0 TR1, 1-2 TR2, 3 TR3, 4-6 TR4, 7+ TR5.
        self.assertEqual(tirads.level_for_points(0), "TR1")
        self.assertEqual(tirads.level_for_points(1), "TR2")
        self.assertEqual(tirads.level_for_points(2), "TR2")
        self.assertEqual(tirads.level_for_points(3), "TR3")
        self.assertEqual(tirads.level_for_points(4), "TR4")
        self.assertEqual(tirads.level_for_points(6), "TR4")
        self.assertEqual(tirads.level_for_points(7), "TR5")
        self.assertEqual(tirads.level_for_points(12), "TR5")

    def test_foci_points_are_additive(self):
        r = tirads.score(
            "solid", "very_hypo", "taller", "ete",
            foci=["macro", "rim", "punctate"],
        )
        # 2 + 3 + 3 + 3 + (1+2+3) = 17
        self.assertEqual(r["points"], 17)
        self.assertEqual(r["level"], "TR5")

    def test_none_focus_ignored_when_combined(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", foci=["none", "punctate"])
        # 2 + 2 + 0 + 0 + 3 = 7
        self.assertEqual(r["points"], 7)
        self.assertEqual(r["level"], "TR5")

    def test_tr4_management_with_size_recommends_fna(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", size_mm=18)  # 4 pts -> TR4
        self.assertEqual(r["level"], "TR4")
        self.assertEqual(r["management"], "FNA recommended.")

    def test_tr4_management_with_size_recommends_followup(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", size_mm=12)  # 1.2 cm
        self.assertIn("Follow-up ultrasound recommended", r["management"])
        self.assertIn("1, 2, 3 and 5 years", r["management"])

    def test_tr4_management_below_threshold(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", size_mm=6)  # 0.6 cm
        self.assertIn("Below the size threshold", r["management"])

    def test_management_without_size_gives_thresholds(self):
        r = tirads.score("solid", "hypo", "wider", "smooth")  # TR4, no size
        self.assertIn("FNA if ≥1.5 cm", r["management"])
        self.assertIn("follow-up ultrasound if ≥1 cm", r["management"])

    def test_report_line_is_paste_ready(self):
        r = tirads.score(
            "mixed", "hypo", "wider", "smooth",
            foci=["punctate"], size_mm=18, location="Right mid pole",
        )
        line = r["report_line"]
        self.assertIn("Right mid pole thyroid nodule measuring 1.8 cm", line)
        self.assertIn("mixed cystic and solid", line)
        self.assertIn("punctate echogenic foci", line)
        self.assertIn("ACR TI-RADS", line)
        self.assertIn(r["level"], line)

    def test_report_line_without_foci_states_none(self):
        r = tirads.score("solid", "hypo", "wider", "smooth")
        self.assertIn("no suspicious echogenic foci", r["report_line"])

    def test_small_size_renders_in_mm(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", size_mm=7)
        self.assertIn("measuring 7 mm", r["report_line"])

    def test_unknown_option_raises(self):
        with self.assertRaises(ValueError):
            tirads.score("banana", "hypo", "wider", "smooth")

    def test_nonpositive_size_ignored(self):
        r = tirads.score("solid", "hypo", "wider", "smooth", size_mm=0)
        self.assertIn("FNA if ≥1.5 cm", r["management"])
        self.assertNotIn("measuring", r["report_line"])


class TiradsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_scores_a_nodule(self):
        resp = self.client.post(
            "/api/tirads/score",
            json={
                "composition": "solid",
                "echogenicity": "very_hypo",
                "shape": "taller",
                "margin": "lobulated",
                "foci": ["punctate"],
                "size_mm": 12,
                "location": "Left lower pole",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["points"], 13)
        self.assertEqual(data["level"], "TR5")
        self.assertIn("Left lower pole thyroid nodule", data["report_line"])

    def test_api_rejects_unknown_option(self):
        resp = self.client.post(
            "/api/tirads/score",
            json={
                "composition": "solid",
                "echogenicity": "hypo",
                "shape": "wider",
                "margin": "not-a-margin",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_does_not_leak_location_beyond_report(self):
        # An 80-char cap protects the report line from abuse; a long location is truncated.
        resp = self.client.post(
            "/api/tirads/score",
            json={
                "composition": "solid", "echogenicity": "hypo",
                "shape": "wider", "margin": "smooth",
                "location": "x" * 500,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.json()["report_line"]), 400)


class TiradsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_page_renders_with_canonical_and_social(self):
        resp = self.client.get("/ti-rads-calculator")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<title>TI-RADS Calculator · RadSpeed</title>', resp.text)
        self.assertIn('<link rel="canonical" href="https://radspeed.com.au/ti-rads-calculator"', resp.text)
        self.assertIn("https://radspeed.com.au/static/radspeed-share.png", resp.text)
        self.assertIn('content="summary_large_image"', resp.text)
        self.assertIn('"@type": "FAQPage"', resp.text)
        self.assertIn("Decision support, not a medical device", resp.text)
        self.assertIn('href="/radiology-reporting-software"', resp.text)
        self.assertIn("<h1>ACR TI-RADS thyroid nodule calculator</h1>", resp.text)
        self.assertIn('href="/report-templates/ultrasound-thyroid"', resp.text)

    def test_sitemap_lists_the_calculator(self):
        resp = self.client.get("/sitemap.xml")
        self.assertIn("<loc>https://radspeed.com.au/ti-rads-calculator</loc>", resp.text)

    def test_llms_file_lists_the_calculator(self):
        resp = self.client.get("/llms.txt")
        self.assertIn("https://radspeed.com.au/ti-rads-calculator", resp.text)

    def test_thyroid_template_links_back_to_calculator(self):
        resp = self.client.get("/report-templates/ultrasound-thyroid")
        self.assertIn('href="/ti-rads-calculator"', resp.text)


if __name__ == "__main__":
    unittest.main()
