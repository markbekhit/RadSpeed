"""Fleischner 2017 pulmonary nodule calculator: rules, API and public page."""

import json
import re
import unittest

from fastapi.testclient import TestClient

from web import fleischner

# NOTE: `web.app` is imported lazily inside setUpClass, never at module import
# time. tests/test_format.py replaces sys.modules["config.config"] with a stub
# at import and never restores it, so any module that first imports the real
# config singleton *before* that stub is installed ends up out of step with
# tests collected afterwards. Importing web.app (which pulls in llm.format) at
# module scope here — this file sorts before test_format — would trip that
# latent ordering hazard, so we defer it.


class FleischnerRuleTests(unittest.TestCase):
    def test_solid_single_low_small_no_followup(self):
        r = fleischner.assess("solid", size_mm=5, multiple=False, risk="low")
        self.assertEqual(r["size_band"], "<6 mm")
        self.assertEqual(r["volume_equivalent"], "<100 mm³")
        self.assertIn("No routine follow-up", r["recommendation"])

    def test_solid_single_high_small_optional_ct(self):
        r = fleischner.assess("solid", size_mm=5, multiple=False, risk="high")
        self.assertIn("Optional CT at 12 months", r["recommendation"])

    def test_solid_single_low_mid_band(self):
        r = fleischner.assess("solid", size_mm=7, multiple=False, risk="low")
        self.assertEqual(r["size_band"], "6–8 mm")
        self.assertEqual(
            r["recommendation"],
            "CT at 6–12 months, then consider CT at 18–24 months.",
        )

    def test_solid_single_high_mid_band_obtains_second_ct(self):
        r = fleischner.assess("solid", size_mm=8, multiple=False, risk="high")
        self.assertEqual(r["size_band"], "6–8 mm")
        self.assertEqual(
            r["recommendation"], "CT at 6–12 months, then CT at 18–24 months."
        )

    def test_solid_large_is_risk_agnostic(self):
        low = fleischner.assess("solid", size_mm=9, risk="low")
        high = fleischner.assess("solid", size_mm=9, risk="high")
        self.assertEqual(low["size_band"], ">8 mm")
        self.assertIn("Consider CT at 3 months", low["recommendation"])
        self.assertEqual(low["recommendation"], high["recommendation"])

    def test_solid_multiple_uses_earlier_first_ct_and_note(self):
        r = fleischner.assess("solid", size_mm=7, multiple=True, risk="low")
        self.assertIn("CT at 3–6 months", r["recommendation"])
        self.assertIn("most suspicious nodule", r["recommendation"])

    def test_band_boundaries_six_and_eight(self):
        # 6 mm and 8 mm are inside the 6–8 band; 8.1 mm is the >8 band.
        self.assertEqual(fleischner.assess("solid", size_mm=6)["size_band"], "6–8 mm")
        self.assertEqual(fleischner.assess("solid", size_mm=8)["size_band"], "6–8 mm")
        self.assertEqual(fleischner.assess("solid", size_mm=8.1)["size_band"], ">8 mm")
        self.assertEqual(fleischner.assess("solid", size_mm=5.9)["size_band"], "<6 mm")

    def test_ground_glass_small_no_routine_followup(self):
        r = fleischner.assess("ground_glass", size_mm=5)
        self.assertFalse(r["risk_applies"])
        self.assertIn("No routine follow-up", r["recommendation"])
        self.assertIn("2 and 4 years", r["recommendation"])

    def test_ground_glass_large_persistence_then_biennial(self):
        r = fleischner.assess("ground_glass", size_mm=7)
        self.assertEqual(r["size_band"], "≥6 mm")
        self.assertIn("confirm persistence", r["recommendation"])
        self.assertIn("every 2 years until 5 years", r["recommendation"])

    def test_ground_glass_risk_does_not_change_output(self):
        low = fleischner.assess("ground_glass", size_mm=7, risk="low")
        high = fleischner.assess("ground_glass", size_mm=7, risk="high")
        self.assertEqual(low["recommendation"], high["recommendation"])

    def test_part_solid_small_no_followup(self):
        r = fleischner.assess("part_solid", size_mm=5)
        self.assertEqual(r["recommendation"], "No routine follow-up is required.")

    def test_part_solid_large_annual_when_solid_component_small(self):
        r = fleischner.assess("part_solid", size_mm=7, solid_component_mm=3)
        self.assertIn("CT at 3–6 months", r["recommendation"])
        self.assertIn("annually for 5 years", r["recommendation"])
        self.assertNotIn("highly suspicious", r["recommendation"])

    def test_part_solid_large_solid_component_flags_suspicion(self):
        r = fleischner.assess("part_solid", size_mm=9, solid_component_mm=6)
        self.assertIn("highly suspicious", r["recommendation"])
        self.assertEqual(r["solid_component_mm"], 6.0)

    def test_multiple_subsolid_shared_recommendation(self):
        gg = fleischner.assess("ground_glass", size_mm=5, multiple=True)
        ps = fleischner.assess("part_solid", size_mm=5, multiple=True)
        self.assertIn("CT at 3–6 months", gg["recommendation"])
        self.assertEqual(gg["recommendation"], ps["recommendation"])

    def test_report_line_is_paste_ready(self):
        r = fleischner.assess(
            "solid", size_mm=7, multiple=False, risk="low", location="right upper lobe"
        )
        line = r["report_line"]
        self.assertIn("Solid pulmonary nodule measuring 7 mm in the right upper lobe", line)
        self.assertIn("Fleischner 2017 (single, low-risk)", line)
        self.assertIn("CT at 6–12 months", line)

    def test_report_line_subsolid_omits_risk(self):
        r = fleischner.assess("ground_glass", size_mm=7)
        self.assertIn("single subsolid", r["report_line"])

    def test_part_solid_report_line_shows_solid_component(self):
        r = fleischner.assess("part_solid", size_mm=9, solid_component_mm=6)
        self.assertIn("solid component 6 mm", r["report_line"])

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            fleischner.assess("cavitary", size_mm=7)

    def test_unknown_risk_raises(self):
        with self.assertRaises(ValueError):
            fleischner.assess("solid", size_mm=7, risk="medium")

    def test_nonpositive_size_raises(self):
        with self.assertRaises(ValueError):
            fleischner.assess("solid", size_mm=0)


class FleischnerMeasurementTests(unittest.TestCase):
    """Mean diameter is the average of both axes, rounded to a whole millimetre."""

    def test_half_millimetre_average_rounds_up(self):
        # 8 x 5 mm averages 6.5 mm and must report as 7 mm, which moves the
        # nodule out of the <6 mm band and into 6-8 mm.
        m = fleischner.mean_diameter(8, 5)
        self.assertEqual(m["average_mm"], 6.5)
        self.assertEqual(m["mean_diameter_mm"], 7)

    def test_axis_order_does_not_matter(self):
        self.assertEqual(
            fleischner.mean_diameter(5, 8), fleischner.mean_diameter(8, 5)
        )

    def test_rounds_down_below_the_half(self):
        self.assertEqual(fleischner.mean_diameter(7, 4)["mean_diameter_mm"], 6)
        self.assertEqual(fleischner.mean_diameter(6, 4)["mean_diameter_mm"], 5)

    def test_rejects_missing_or_nonpositive_axis(self):
        with self.assertRaises(ValueError):
            fleischner.mean_diameter(8, 0)
        with self.assertRaises(ValueError):
            fleischner.mean_diameter(None, 5)

    def test_assess_accepts_axes_and_uses_the_rounded_mean(self):
        r = fleischner.assess("solid", long_axis_mm=8, short_axis_mm=5, risk="low")
        self.assertEqual(r["size_mm"], 7)
        self.assertEqual(r["size_band"], "6–8 mm")
        self.assertEqual(r["measurement"]["mean_diameter_mm"], 7)
        self.assertIn("7 mm", r["report_line"])

    def test_assess_without_any_size_is_rejected(self):
        with self.assertRaises(ValueError):
            fleischner.assess("solid")

    def test_assess_without_axes_reports_no_measurement_block(self):
        self.assertIsNone(fleischner.assess("solid", size_mm=7)["measurement"])


class FleischnerComparisonTests(unittest.TestCase):
    """Interval change against the prior study."""

    def test_two_millimetre_increase_is_growth(self):
        c = fleischner.compare_prior(8, 6, interval_months=12)
        self.assertEqual(c["status"], "growth")
        self.assertTrue(c["grew"])
        self.assertEqual(c["diameter_change_mm"], 2.0)
        self.assertIn("12 months", c["summary"])
        self.assertIsNotNone(c["growth_note"])

    def test_smaller_increase_stays_stable(self):
        c = fleischner.compare_prior(7.9, 6, interval_months=12)
        self.assertEqual(c["status"], "stable")
        self.assertFalse(c["grew"])
        self.assertIn("measurement variability", c["summary"])
        self.assertIsNone(c["growth_note"])

    def test_two_millimetre_decrease_is_smaller(self):
        c = fleischner.compare_prior(6, 8)
        self.assertEqual(c["status"], "smaller")
        self.assertFalse(c["grew"])

    def test_volume_growth_above_twenty_five_percent(self):
        c = fleischner.compare_prior(7, 6, volume_mm3=200, prior_volume_mm3=100)
        self.assertEqual(c["diameter_status"], "stable")
        self.assertEqual(c["volume_status"], "growth")
        self.assertEqual(c["status"], "growth")
        self.assertEqual(c["volume_change_percent"], 100.0)

    def test_volume_inside_threshold_stays_stable(self):
        c = fleischner.compare_prior(7, 6, volume_mm3=120, prior_volume_mm3=100)
        self.assertEqual(c["volume_status"], "stable")
        self.assertEqual(c["status"], "stable")

    def test_one_volume_alone_is_ignored(self):
        c = fleischner.compare_prior(7, 6, volume_mm3=200)
        self.assertIsNone(c["volume_status"])
        self.assertIsNone(c["volume_change_percent"])

    def test_zero_interval_is_dropped_rather_than_printed(self):
        c = fleischner.compare_prior(8, 6, interval_months=0)
        self.assertIsNone(c["interval_months"])
        self.assertNotIn("months", c["summary"])

    def test_assess_appends_the_comparison_to_the_report_line(self):
        r = fleischner.assess("solid", size_mm=8, prior_size_mm=5, interval_months=6)
        self.assertEqual(r["comparison"]["status"], "growth")
        self.assertIn("Mean diameter 5 mm to 8 mm", r["report_line"])
        self.assertIn("Reassess management", r["report_line"])

    def test_assess_without_a_prior_reports_no_comparison(self):
        self.assertIsNone(fleischner.assess("solid", size_mm=7)["comparison"])

    def test_comparison_uses_the_rounded_mean_not_the_raw_average(self):
        # 8 x 5 mm rounds to 7 mm, so against a 5 mm prior the change is 2 mm
        # and counts as growth. The unrounded 6.5 mm would not.
        r = fleischner.assess(
            "solid", long_axis_mm=8, short_axis_mm=5, prior_size_mm=5
        )
        self.assertEqual(r["comparison"]["diameter_change_mm"], 2.0)
        self.assertEqual(r["comparison"]["status"], "growth")


class FleischnerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_api_recommends(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={
                "nodule_type": "solid",
                "size_mm": 7,
                "multiple": False,
                "risk": "high",
                "location": "left lower lobe",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["size_band"], "6–8 mm")
        self.assertIn("CT at 18–24 months", data["recommendation"])
        self.assertIn("left lower lobe", data["report_line"])

    def test_api_rejects_unknown_type(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={"nodule_type": "not-a-type", "size_mm": 7},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_rejects_nonpositive_size(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={"nodule_type": "solid", "size_mm": 0},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_accepts_axes_and_a_prior(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={
                "nodule_type": "solid",
                "long_axis_mm": 8,
                "short_axis_mm": 5,
                "prior_size_mm": 5,
                "interval_months": 12,
                "risk": "low",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["measurement"]["mean_diameter_mm"], 7)
        self.assertEqual(data["size_band"], "6–8 mm")
        self.assertEqual(data["comparison"]["status"], "growth")

    def test_api_rejects_a_request_with_no_size_at_all(self):
        resp = self.client.post(
            "/api/fleischner/recommend", json={"nodule_type": "solid"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_rejects_a_nonpositive_prior(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={"nodule_type": "solid", "size_mm": 7, "prior_size_mm": 0},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_truncates_long_location(self):
        resp = self.client.post(
            "/api/fleischner/recommend",
            json={"nodule_type": "solid", "size_mm": 7, "location": "x" * 500},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.json()["report_line"]), 400)


class FleischnerPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_page_renders_with_canonical_and_social(self):
        resp = self.client.get("/fleischner-calculator")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<title>Fleischner Calculator · RadSpeed</title>", resp.text)
        self.assertIn(
            '<link rel="canonical" href="https://radspeed.com.au/fleischner-calculator"',
            resp.text,
        )
        self.assertIn("https://radspeed.com.au/static/radspeed-share.png", resp.text)
        self.assertIn('content="summary_large_image"', resp.text)
        self.assertIn('"@type": "FAQPage"', resp.text)
        self.assertIn("Decision support, not a medical device", resp.text)
        self.assertIn("<h1>Fleischner 2017 pulmonary nodule calculator</h1>", resp.text)
        self.assertIn('href="/report-templates/ct-chest"', resp.text)

    def test_page_exposes_the_axis_and_prior_inputs(self):
        resp = self.client.get("/fleischner-calculator")
        for field in (
            "long_axis_mm",
            "short_axis_mm",
            "prior_size_mm",
            "interval_months",
            "volume_mm3",
            "prior_volume_mm3",
        ):
            self.assertIn(f'id="{field}"', resp.text, field)
        self.assertIn('id="interval-change"', resp.text)
        self.assertIn('id="measurement-note"', resp.text)

    def test_page_states_the_measurement_and_growth_rules(self):
        resp = self.client.get("/fleischner-calculator")
        self.assertIn("Measuring the nodule", resp.text)
        self.assertIn("Comparing with the prior study", resp.text)
        self.assertIn("Bankier", resp.text)

    def test_page_faq_schema_stays_valid_json(self):
        resp = self.client.get("/fleischner-calculator")
        block = re.search(
            r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
            resp.text,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        graph = json.loads(block.group(1))["@graph"]
        faq = next(node for node in graph if node["@type"] == "FAQPage")
        names = [q["name"] for q in faq["mainEntity"]]
        self.assertIn(
            "How much does a lung nodule have to grow to count as growth?", names
        )

    def test_sitemap_lists_the_calculator(self):
        resp = self.client.get("/sitemap.xml")
        self.assertIn("<loc>https://radspeed.com.au/fleischner-calculator</loc>", resp.text)

    def test_llms_file_lists_the_calculator(self):
        resp = self.client.get("/llms.txt")
        self.assertIn("https://radspeed.com.au/fleischner-calculator", resp.text)

    def test_ct_chest_template_links_to_calculator(self):
        resp = self.client.get("/report-templates/ct-chest")
        self.assertIn('href="/fleischner-calculator"', resp.text)


if __name__ == "__main__":
    unittest.main()
