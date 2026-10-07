"""Lung nodule volume doubling time calculator: rules, API and public page."""

import unittest

from fastapi.testclient import TestClient

from web import nodule_growth

# NOTE: `web.app` is imported lazily inside setUpClass, never at module import
# time. See tests/test_fleischner.py for the ordering hazard this avoids.


class NoduleGrowthRuleTests(unittest.TestCase):
    def test_volume_doubling_time_uses_schwartz_formula(self):
        r = nodule_growth.assess(prior=120, current=180, interval_days=182)
        # 182 x ln2 / ln(1.5) == 311.1
        self.assertEqual(r["vdt_days"], 311)
        self.assertEqual(r["volume_change_percent"], 50.0)
        self.assertEqual(r["nlcsp_status"], "growing")
        self.assertEqual(r["bts_band"], "fast")

    def test_exact_doubling_equals_interval(self):
        r = nodule_growth.assess(prior=100, current=200, interval_days=450)
        self.assertEqual(r["vdt_days"], 450)
        self.assertEqual(r["bts_band"], "intermediate")

    def test_growth_over_600_days_is_single_interval_slow_pattern(self):
        r = nodule_growth.assess(prior=100, current=130, interval_days=730)
        self.assertGreater(r["vdt_days"], 600)
        self.assertEqual(r["nlcsp_status"], "slow_growth_pattern")
        self.assertIn("more than one scan interval", r["nlcsp_text"])
        self.assertEqual(r["bts_band"], "slow")

    def test_volume_change_boundaries(self):
        self.assertEqual(nodule_growth.assess(100, 125, 365)["nlcsp_status"], "stable")
        self.assertEqual(nodule_growth.assess(100, 125.1, 90)["nlcsp_status"], "growing")
        self.assertEqual(nodule_growth.assess(100, 75, 365)["nlcsp_status"], "decreased")
        self.assertEqual(nodule_growth.assess(100, 75.1, 365)["nlcsp_status"], "stable")
        # BTS counts 25% or more as significant growth.
        self.assertEqual(nodule_growth.assess(100, 125, 90)["bts_band"], "fast")
        self.assertEqual(nodule_growth.assess(100, 124.9, 90)["bts_band"], "stable")

    def test_no_vdt_without_volume_increase(self):
        r = nodule_growth.assess(prior=150, current=100, interval_days=365)
        self.assertIsNone(r["vdt_days"])
        self.assertIn("no volume increase", r["report_line"])

    def test_small_change_warns_that_vdt_is_unreliable(self):
        r = nodule_growth.assess(prior=100, current=110, interval_days=365)
        self.assertIsNotNone(r["vdt_days"])
        self.assertTrue(any("measurement error" in w for w in r["warnings"]))

    def test_diameter_mode_estimates_sphere_volume(self):
        r = nodule_growth.assess(prior=6, current=7, interval_days=365, method="diameter")
        # (7/6)^3 == 1.588 -> +58.8%, VDT 547 days
        self.assertEqual(r["volume_change_percent"], 58.8)
        self.assertEqual(r["vdt_days"], 547)
        self.assertEqual(r["diameter_change_mm"], 1.0)
        # A 1.0 mm diameter change is stable under the NLCSP diameter rule.
        self.assertEqual(r["nlcsp_status"], "stable")
        self.assertIsNone(r["bts_band"])
        self.assertEqual(
            r["report_line"],
            "Pulmonary nodule: mean diameter 7.0 mm, previously 6.0 mm "
            "(365 days earlier); mean diameter change +1.0 mm, within measurement error.",
        )

    def test_diameter_growth_line_reports_diameter_change_and_estimated_vdt(self):
        r = nodule_growth.assess(6, 7.6, 365, method="diameter")
        self.assertEqual(r["nlcsp_status"], "growing")
        self.assertIn("mean diameter change +1.6 mm", r["report_line"])
        self.assertIn(f"estimated volume doubling time {r['vdt_days']} days (from mean diameter).", r["report_line"])
        self.assertNotIn("volume change", r["report_line"].replace("mean diameter change", ""))
        self.assertEqual(r["report_line"].count("("), 2)
        down = nodule_growth.assess(6, 4.4, 365, method="diameter")
        self.assertTrue(down["report_line"].endswith("mean diameter change -1.6 mm."))

    def test_diameter_growth_splits_at_24_months(self):
        fast = nodule_growth.assess(6, 8, 700, method="diameter")
        slow = nodule_growth.assess(6, 8, 800, method="diameter")
        self.assertEqual(fast["nlcsp_status"], "growing")
        self.assertEqual(slow["nlcsp_status"], "slowly_growing")
        self.assertEqual(nodule_growth.assess(6, 7.5, 365, method="diameter")["nlcsp_status"], "stable")
        self.assertEqual(nodule_growth.assess(6, 4.5, 365, method="diameter")["nlcsp_status"], "decreased")

    def test_report_line_has_no_dates(self):
        r = nodule_growth.assess(120, 180, 182)
        self.assertEqual(
            r["report_line"],
            "Pulmonary nodule: volume 180 mm³, previously 120 mm³ "
            "(182 days earlier); volume change +50%, volume doubling time 311 days.",
        )

    def test_one_decimal_diameters_hold_the_1_5_mm_boundary(self):
        # Floating-point subtraction gives 1.5000000000000002 for these pairs.
        for prior, current, status in (
            (6.8, 8.3, "stable"),
            (7.3, 8.8, "stable"),
            (14.6, 16.1, "stable"),
            (3.9, 5.4, "stable"),
            (8.2, 6.7, "decreased"),
            (4.1, 2.6, "decreased"),
            (16.9, 15.4, "decreased"),
        ):
            r = nodule_growth.assess(prior, current, 365, method="diameter")
            self.assertEqual(r["nlcsp_status"], status, (prior, current))

    def test_readings_use_the_displayed_rounded_vdt(self):
        # 599.6 days displays as 600, so it must not read as under 600 days.
        r = nodule_growth.assess(100, 200, 599.6)
        self.assertEqual(r["vdt_days"], 600)
        self.assertEqual(r["nlcsp_status"], "slow_growth_pattern")
        self.assertEqual(r["bts_band"], "intermediate")
        # 399.7 days displays as 400, so it sits in the 400-600 band.
        r = nodule_growth.assess(100, 200, 399.7)
        self.assertEqual(r["vdt_days"], 400)
        self.assertEqual(r["bts_band"], "intermediate")
        self.assertEqual(nodule_growth.assess(100, 200, 399.4)["bts_band"], "fast")

    def test_two_years_across_a_leap_day_count_as_24_months(self):
        for days, status in (
            (730, "growing"),
            (731, "growing"),
            (732, "growing"),
            (733, "slowly_growing"),
        ):
            r = nodule_growth.assess(6, 8, days, method="diameter")
            self.assertEqual(r["nlcsp_status"], status, days)

    def test_tiny_decrease_has_no_negative_zero(self):
        r = nodule_growth.assess(100, 99.99, 365)
        self.assertIn("volume change +0%", r["report_line"])

    def test_report_line_omits_vdt_inside_measurement_error(self):
        r = nodule_growth.assess(100, 120, 60)
        self.assertEqual(r["nlcsp_status"], "stable")
        self.assertNotIn("doubling time 2", r["report_line"])
        self.assertIn("within measurement error", r["report_line"])
        d = nodule_growth.assess(5.0, 6.5, 100, method="diameter")
        self.assertEqual(d["nlcsp_status"], "stable")
        self.assertIn("mean diameter change +1.5 mm, within measurement error.", d["report_line"])
        self.assertNotIn("doubling time", d["report_line"])
        self.assertTrue(any("±1.5 mm" in w for w in d["warnings"]))

    def test_bts_reads_a_decrease_as_not_applicable(self):
        r = nodule_growth.assess(100, 60, 365)
        self.assertEqual(r["bts_band"], "decreased")
        self.assertIn("do not apply", r["bts_text"])

    def test_exactly_25_percent_explains_the_framework_difference(self):
        r = nodule_growth.assess(100, 125, 90)
        self.assertEqual(r["nlcsp_status"], "stable")
        self.assertEqual(r["bts_band"], "fast")
        self.assertTrue(any("exactly 25%" in w for w in r["warnings"]))

    def test_volumes_report_to_the_nearest_whole_mm3(self):
        r = nodule_growth.assess(120.4, 180.6, 182)
        self.assertIn("volume 181 mm³, previously 120 mm³", r["report_line"])

    def test_single_day_is_singular(self):
        self.assertIn("(1 day earlier)", nodule_growth.assess(100, 200, 1)["report_line"])

    def test_extreme_values_are_rejected_not_overflowed(self):
        for kwargs in (
            dict(prior=1e-300, current=1e300, interval_days=100),
            dict(prior=1e-200, current=1e200, interval_days=100, method="diameter"),
        ):
            with self.assertRaises(ValueError):
                nodule_growth.assess(**kwargs)

    def test_rejects_invalid_input(self):
        for kwargs in (
            dict(prior=0, current=100, interval_days=90),
            dict(prior=100, current=-1, interval_days=90),
            dict(prior=100, current=120, interval_days=0),
            dict(prior=100, current=120, interval_days=0.5),
            dict(prior=100, current=120, interval_days=90, method="area"),
            dict(prior="x", current=120, interval_days=90),
            dict(prior=float("nan"), current=120, interval_days=90),
        ):
            with self.assertRaises(ValueError, msg=kwargs):
                nodule_growth.assess(**kwargs)

    def test_short_interval_warns(self):
        r = nodule_growth.assess(100, 150, 14)
        self.assertTrue(any("four weeks" in w for w in r["warnings"]))


class NoduleGrowthApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_api_calculates(self):
        resp = self.client.post(
            "/api/nodule-growth/vdt",
            json={"prior": 120, "current": 180, "interval_days": 182},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["vdt_days"], 311)
        self.assertEqual(body["nlcsp_status"], "growing")

    def test_api_rejects_bad_values(self):
        resp = self.client.post(
            "/api/nodule-growth/vdt",
            json={"prior": 120, "current": 180, "interval_days": -5},
        )
        self.assertEqual(resp.status_code, 400)


class NoduleGrowthPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app

        cls.client = TestClient(app)

    def test_page_renders_with_canonical_schema_and_sources(self):
        resp = self.client.get("/volume-doubling-time-calculator")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "<title>Lung Nodule Volume Doubling Time Calculator · RadSpeed</title>", resp.text
        )
        self.assertIn(
            '<link rel="canonical" href="https://radspeed.com.au/volume-doubling-time-calculator"',
            resp.text,
        )
        self.assertIn('"@type": "FAQPage"', resp.text)
        self.assertIn("nlcsp-nodule-management-protocol", resp.text)
        self.assertIn('href="/fleischner-calculator"', resp.text)
        self.assertIn("/static/nodule-growth.js", resp.text)

    def test_page_is_in_sitemap_llms_and_head(self):
        self.assertIn(
            "https://radspeed.com.au/volume-doubling-time-calculator",
            self.client.get("/sitemap.xml").text,
        )
        self.assertIn("/volume-doubling-time-calculator", self.client.get("/llms.txt").text)
        self.assertEqual(self.client.head("/volume-doubling-time-calculator").status_code, 200)

    def test_related_pages_link_to_the_calculator(self):
        for path in (
            "/",
            "/fleischner-calculator",
            "/impressions",
            "/report-templates",
            "/report-templates/ct-chest",
        ):
            resp = self.client.get(path)
            self.assertIn('href="/volume-doubling-time-calculator"', resp.text, path)


if __name__ == "__main__":
    unittest.main()
