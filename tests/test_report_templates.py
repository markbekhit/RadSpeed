"""Public report-template library: rendering, safety and SEO wiring.

The library is a public marketing surface. Its regression guarantees are:
  1. Every curated template renders a valid, substantial detail page.
  2. No proprietary prompt text, ASR lexicon or `**Instructions:**` block ever
     reaches a public page — only the exam name and technique are read from the
     real bundled templates.
  3. Every catalogue entry is discoverable (sitemap, internal links) and each
     page carries a canonical URL.
"""

import unittest

from fastapi.testclient import TestClient

import web.report_templates as rt
from web.app import app

# Text that must never appear on a public page. These strings live inside the
# bundled template files but are proprietary prompt engineering / ASR-only.
FORBIDDEN = [
    "**Instructions:**",
    "correct spellings",
    "CONTINUATION OF SYSTEM PROMPT",
    "AI INSTRUCTIONS",
    "ASR Prompt",
]


class ReportTemplateLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_library_covers_the_expected_studies(self):
        # Guards against a curated entry silently losing its modality group.
        self.assertGreaterEqual(rt.library_count(), 39)
        grouped = {e["slug"] for g in rt.library_groups() for e in g["entries"]}
        self.assertEqual(grouped, set(rt.all_slugs()))

    def test_parsed_exam_and_technique_match_the_real_templates(self):
        # The two live-parsed fields must be populated for every entry.
        for slug in rt.all_slugs():
            entry = rt.get_entry(slug)
            self.assertTrue(entry["exam"], f"missing exam for {slug}")
            self.assertTrue(entry["technique"], f"missing technique for {slug}")

    def test_index_page_renders_with_seo_foundations(self):
        response = self.client.get("/report-templates")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn(
            '<link rel="canonical" href="https://radspeed.com.au/report-templates"',
            body,
        )
        self.assertIn('"@type": "CollectionPage"', body)
        self.assertIn("Radiology report templates", body)
        self.assertIn('href="/impressions"', body)
        for forbidden in FORBIDDEN:
            self.assertNotIn(forbidden, body)

    def test_every_detail_page_renders_safely(self):
        for slug in rt.all_slugs():
            response = self.client.get(f"/report-templates/{slug}")
            self.assertEqual(response.status_code, 200, slug)
            body = response.text
            self.assertGreater(len(body), 2000, slug)
            self.assertIn(
                f'<link rel="canonical" href="https://radspeed.com.au/report-templates/{slug}"',
                body,
            )
            self.assertIn('"@type": "BreadcrumbList"', body)
            self.assertIn("report template", body)
            self.assertIn('href="/impressions"', body)
            self.assertNotIn("Structured Reporting · RadSpeed</title>", body)
            self.assertIn(
                f"<title>{rt.get_entry(slug)['seo_title']} Report Template · RadSpeed</title>",
                body,
            )
            self.assertIn("https://radspeed.com.au/static/radspeed-share.png", body)
            for forbidden in FORBIDDEN:
                self.assertNotIn(forbidden, body, f"{forbidden!r} leaked on {slug}")

    def test_unknown_template_returns_404(self):
        self.assertEqual(
            self.client.get("/report-templates/not-a-real-study").status_code, 404
        )

    def test_sitemap_lists_the_library_index_and_every_detail_page(self):
        body = self.client.get("/sitemap.xml").text
        self.assertIn("<loc>https://radspeed.com.au/report-templates</loc>", body)
        for slug in rt.all_slugs():
            self.assertIn(
                f"<loc>https://radspeed.com.au/report-templates/{slug}</loc>", body
            )

    def test_home_and_llms_link_to_the_library(self):
        self.assertIn("/report-templates", self.client.get("/").text)
        self.assertIn(
            "https://radspeed.com.au/report-templates", self.client.get("/llms.txt").text
        )


if __name__ == "__main__":
    unittest.main()
