"""Public search-discovery routes and metadata."""

import unittest

from fastapi.testclient import TestClient

from web.app import app


class PublicSEOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_robots_lists_sitemap_and_protects_private_routes(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sitemap: https://radspeed.com.au/sitemap.xml", response.text)
        self.assertIn("Disallow: /api/", response.text)
        self.assertIn("Disallow: /app", response.text)

    def test_sitemap_contains_only_public_indexable_pages(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/xml"))
        self.assertIn("<loc>https://radspeed.com.au/</loc>", response.text)
        self.assertIn("<loc>https://radspeed.com.au/radiology-reporting-software</loc>", response.text)
        self.assertIn("<loc>https://radspeed.com.au/powerscribe-companion</loc>", response.text)
        self.assertIn("<loc>https://radspeed.com.au/impressions</loc>", response.text)
        self.assertNotIn("/app</loc>", response.text)

    def test_head_requests_match_public_get_routes_without_a_body(self):
        for path in (
            "/",
            "/impressions",
            "/radiology-reporting-software",
            "/powerscribe-companion",
            "/ti-rads-calculator",
            "/fleischner-calculator",
            "/adrenal-washout-calculator",
            "/report-templates",
        ):
            get_response = self.client.get(path)
            head_response = self.client.head(path)
            self.assertEqual(head_response.status_code, get_response.status_code, path)
            self.assertEqual(head_response.content, b"", path)
            self.assertEqual(
                head_response.headers["content-type"],
                get_response.headers["content-type"],
                path,
            )
        self.assertEqual(self.client.head("/api/impressions/text").status_code, 405)
        self.assertEqual(self.client.head("/not-a-public-page").status_code, 404)

    def test_llms_file_states_public_pages_and_limits(self):
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("## Public pages", response.text)
        self.assertIn("Do not infer diagnostic performance", response.text)

    def test_impressions_has_canonical_and_social_metadata(self):
        response = self.client.get("/impressions")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1>Radiology impression generator</h1>", response.text)
        self.assertIn('<link rel="canonical" href="https://radspeed.com.au/impressions"', response.text)
        self.assertIn('<meta property="og:url" content="https://radspeed.com.au/impressions"', response.text)
        self.assertIn('<meta property="og:image" content="https://radspeed.com.au/static/radspeed-share.png"', response.text)
        self.assertIn('<meta name="twitter:card" content="summary_large_image"', response.text)
        self.assertIn('"@type": "WebApplication"', response.text)
        self.assertIn('data-example="ct-chest"', response.text)
        self.assertIn("Paste de-identified findings", response.text)
        self.assertIn('href="/report-templates"', response.text)
        self.assertIn('href="/fleischner-calculator"', response.text)
        self.assertNotIn("under two seconds", response.text)

    def test_homepage_exposes_free_reporting_tools(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Use the narrow tool that matches the task", response.text)
        self.assertIn('href="/impressions"', response.text)
        self.assertIn('href="/ti-rads-calculator"', response.text)
        self.assertIn('href="/fleischner-calculator"', response.text)
        self.assertIn('href="/adrenal-washout-calculator"', response.text)
        self.assertIn('href="/report-templates"', response.text)

    def test_public_pages_have_large_social_preview_metadata(self):
        for path in (
            "/",
            "/impressions",
            "/radiology-reporting-software",
            "/powerscribe-companion",
            "/report-templates",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("https://radspeed.com.au/static/radspeed-share.png", response.text, path)
            self.assertIn('content="summary_large_image"', response.text, path)

        image = self.client.get("/static/radspeed-share.png")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")
        self.assertTrue(image.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_search_console_verification_file_is_available_at_site_root(self):
        response = self.client.get("/googleb219a940c12a9cd3.html")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text,
            "google-site-verification: googleb219a940c12a9cd3.html",
        )

    def test_public_page_titles_keep_the_specific_query_first(self):
        self.assertIn(
            "<title>Radiology Reporting Software · RadSpeed</title>",
            self.client.get("/radiology-reporting-software").text,
        )
        self.assertIn(
            "<title>Radiology Report Templates · RadSpeed</title>",
            self.client.get("/report-templates").text,
        )
        self.assertIn(
            "<title>PowerScribe Companion for Windows · RadSpeed</title>",
            self.client.get("/powerscribe-companion").text,
        )

    def test_reporting_software_page_has_search_and_conversion_foundations(self):
        response = self.client.get("/radiology-reporting-software")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<link rel="canonical" href="https://radspeed.com.au/radiology-reporting-software"', response.text)
        self.assertIn("Finish reports faster. Keep your reporting style", response.text)
        self.assertIn("Your report should not read like the software wrote it", response.text)
        self.assertIn("RadSpeed drafts. You decide", response.text)
        self.assertIn('class="workstation"', response.text)
        self.assertIn("MR Lumbar Spine", response.text)
        self.assertIn("4 mm right paracentral protrusion", response.text)
        self.assertIn("De-identified synthetic case", response.text)
        self.assertIn("Technique", response.text)
        self.assertIn("Clinical details", response.text)
        self.assertIn("Comparison", response.text)
        self.assertIn("Template applied", response.text)
        self.assertIn("Sections ordered", response.text)
        self.assertIn("Anatomical order", response.text)
        self.assertIn('href="/app"', response.text)
        self.assertIn('"@type": "SoftwareApplication"', response.text)

    def test_powerscribe_companion_page_has_product_and_conversion_foundations(self):
        response = self.client.get("/powerscribe-companion")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<link rel="canonical" href="https://radspeed.com.au/powerscribe-companion"',
            response.text,
        )
        self.assertIn("Keep PowerScribe open. Add a faster impression step", response.text)
        self.assertIn("Select findings", response.text)
        self.assertIn("Press Ctrl+I", response.text)
        self.assertIn("Unknown publisher", response.text)
        self.assertIn("RadSpeed is not affiliated with Microsoft", response.text)
        self.assertIn('href="/impressions"', response.text)
        self.assertIn('href="/app"', response.text)
        self.assertIn('"@type": "SoftwareApplication"', response.text)


if __name__ == "__main__":
    unittest.main()
