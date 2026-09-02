"""Adrenal CT washout calculator: rules, API and public page."""

import unittest

from fastapi.testclient import TestClient

from web import adrenal

# NOTE: `web.app` is imported lazily inside setUpClass, never at module import
# time. tests/test_format.py replaces sys.modules["config.config"] with a stub
# at import and never restores it, so importing web.app at module scope here —
# this file sorts before test_format — would trip that latent ordering hazard.
# See tests/test_fleischner.py for the same guard.


class AdrenalRuleTests(unittest.TestCase):
    def test_absolute_washout_at_threshold_is_adenoma(self):
        r = adrenal.assess(enhanced_hu=78, delayed_hu=42, unenhanced_hu=18)
        # (78-42)/(78-18)*100 == 60.0
        self.assertEqual(r["apw"], 60.0)
        self.assertTrue(r["apw_meets"])
        self.assertEqual(r["category"], "lipid_poor_adenoma")
        self.assertTrue(r["washout_positive"])
        self.assertEqual(r["primary_metric"], "APW")

    def test_relative_washout_reported_alongside_absolute(self):
        r = adrenal.assess(enhanced_hu=78, delayed_hu=42, unenhanced_hu=18)
        # (78-42)/78*100 == 46.2 (1 dp)
        self.assertEqual(r["rpw"], 46.2)

    def test_low_absolute_washout_is_indeterminate(self):
        r = adrenal.assess(enhanced_hu=78, delayed_hu=60, unenhanced_hu=40)
        self.assertFalse(r["apw_meets"])
        self.assertEqual(r["category"], "indeterminate")
        self.assertFalse(r["washout_positive"])
        self.assertIn("indeterminate", r["recommendation"])

    def test_lipid_rich_shortcut_when_unenhanced_low(self):
        r = adrenal.assess(enhanced_hu=40, delayed_hu=30, unenhanced_hu=6)
        self.assertTrue(r["lipid_rich_adenoma"])
        self.assertEqual(r["category"], "lipid_rich_adenoma")
        self.assertIn("lipid-rich adenoma", r["recommendation"])

    def test_ten_hu_boundary_is_lipid_rich(self):
        self.assertTrue(adrenal.assess(80, 40, unenhanced_hu=10)["lipid_rich_adenoma"])
        self.assertFalse(adrenal.assess(80, 40, unenhanced_hu=10.1)["lipid_rich_adenoma"])

    def test_relative_only_when_no_unenhanced_phase(self):
        r = adrenal.assess(enhanced_hu=80, delayed_hu=40)
        self.assertIsNone(r["apw"])
        self.assertEqual(r["rpw"], 50.0)
        self.assertEqual(r["primary_metric"], "RPW")
        self.assertTrue(r["rpw_meets"])
        self.assertEqual(r["category"], "lipid_poor_adenoma")

    def test_relative_only_below_threshold_is_indeterminate(self):
        r = adrenal.assess(enhanced_hu=80, delayed_hu=60)
        self.assertEqual(r["rpw"], 25.0)
        self.assertEqual(r["category"], "indeterminate")

    def test_no_enhancement_drops_absolute_washout(self):
        # Enhanced is not above unenhanced, so the absolute ratio is undefined.
        r = adrenal.assess(enhanced_hu=45, delayed_hu=40, unenhanced_hu=50)
        self.assertIsNone(r["apw"])
        self.assertIsNotNone(r["rpw"])
        self.assertEqual(r["primary_metric"], "RPW")

    def test_equal_enhanced_and_unenhanced_avoids_division_by_zero(self):
        r = adrenal.assess(enhanced_hu=40, delayed_hu=20, unenhanced_hu=40)
        self.assertIsNone(r["apw"])
        self.assertEqual(r["rpw"], 50.0)

    def test_macroscopic_fat_note_added(self):
        r = adrenal.assess(enhanced_hu=40, delayed_hu=30, unenhanced_hu=-30)
        self.assertTrue(r["macroscopic_fat"])
        self.assertIn("macroscopic fat", r["recommendation"])

    def test_negative_washout_is_indeterminate(self):
        # Delayed higher than enhanced (contrast accumulation) — no washout.
        r = adrenal.assess(enhanced_hu=60, delayed_hu=70, unenhanced_hu=30)
        self.assertLess(r["apw"], 0)
        self.assertEqual(r["category"], "indeterminate")

    def test_report_line_is_paste_ready(self):
        r = adrenal.assess(
            enhanced_hu=78, delayed_hu=42, unenhanced_hu=18, size_mm=22, location="right"
        )
        line = r["report_line"]
        self.assertIn("right adrenal nodule measuring 22 mm", line)
        self.assertIn("unenhanced 18 HU", line)
        self.assertIn("portal venous 78 HU", line)
        self.assertIn("15-minute delayed 42 HU", line)
        self.assertIn("absolute washout 60%", line)
        self.assertIn("lipid-poor adenoma", line)

    def test_report_line_lipid_rich_is_concise(self):
        r = adrenal.assess(enhanced_hu=40, delayed_hu=30, unenhanced_hu=6, location="left")
        self.assertIn("unenhanced attenuation 6 HU", r["report_line"])
        self.assertIn("lipid-rich adenoma", r["report_line"])

    def test_report_line_relative_only_omits_unenhanced(self):
        r = adrenal.assess(enhanced_hu=80, delayed_hu=40)
        self.assertNotIn("unenhanced", r["report_line"])
        self.assertIn("relative washout 50%", r["report_line"])

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            adrenal.assess(enhanced_hu="abc", delayed_hu=40)

    def test_uncalculable_raises(self):
        with self.assertRaises(ValueError):
            adrenal.assess(enhanced_hu=0, delayed_hu=0)


class AdrenalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_api_calculates(self):
        resp = self.client.post(
            "/api/adrenal/washout",
            json={
                "enhanced_hu": 78,
                "delayed_hu": 42,
                "unenhanced_hu": 18,
                "size_mm": 22,
                "location": "right",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["apw"], 60.0)
        self.assertEqual(data["category"], "lipid_poor_adenoma")
        self.assertIn("right adrenal nodule", data["report_line"])

    def test_api_relative_only(self):
        resp = self.client.post(
            "/api/adrenal/washout",
            json={"enhanced_hu": 80, "delayed_hu": 40},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["apw"])
        self.assertEqual(resp.json()["rpw"], 50.0)

    def test_api_rejects_uncalculable(self):
        resp = self.client.post(
            "/api/adrenal/washout",
            json={"enhanced_hu": 0, "delayed_hu": 0},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_truncates_long_location(self):
        resp = self.client.post(
            "/api/adrenal/washout",
            json={"enhanced_hu": 78, "delayed_hu": 42, "location": "x" * 500},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.json()["report_line"]), 400)


class AdrenalPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_page_renders_with_canonical_and_social(self):
        resp = self.client.get("/adrenal-washout-calculator")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<title>Adrenal Washout Calculator · RadSpeed</title>", resp.text)
        self.assertIn(
            '<link rel="canonical" href="https://radspeed.com.au/adrenal-washout-calculator"',
            resp.text,
        )
        self.assertIn("https://radspeed.com.au/static/radspeed-share.png", resp.text)
        self.assertIn('content="summary_large_image"', resp.text)
        self.assertIn('"@type": "FAQPage"', resp.text)
        self.assertIn("Decision support, not a medical device", resp.text)
        self.assertIn("<h1>Adrenal CT washout calculator</h1>", resp.text)
        self.assertIn('href="/report-templates/ct-abdomen-pelvis"', resp.text)

    def test_sitemap_lists_the_calculator(self):
        resp = self.client.get("/sitemap.xml")
        self.assertIn(
            "<loc>https://radspeed.com.au/adrenal-washout-calculator</loc>", resp.text
        )

    def test_llms_file_lists_the_calculator(self):
        resp = self.client.get("/llms.txt")
        self.assertIn("https://radspeed.com.au/adrenal-washout-calculator", resp.text)

    def test_ct_abdomen_template_links_to_calculator(self):
        resp = self.client.get("/report-templates/ct-abdomen-pelvis")
        self.assertIn('href="/adrenal-washout-calculator"', resp.text)

    def test_homepage_lists_the_calculator(self):
        resp = self.client.get("/")
        self.assertIn('href="/adrenal-washout-calculator"', resp.text)


if __name__ == "__main__":
    unittest.main()
