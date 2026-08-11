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
        self.assertIn("<loc>https://radspeed.com.au/impressions</loc>", response.text)
        self.assertNotIn("/app</loc>", response.text)

    def test_llms_file_states_public_pages_and_limits(self):
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("## Public pages", response.text)
        self.assertIn("Do not infer diagnostic performance", response.text)

    def test_impressions_has_canonical_and_social_metadata(self):
        response = self.client.get("/impressions")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<link rel="canonical" href="https://radspeed.com.au/impressions"', response.text)
        self.assertIn('<meta property="og:url" content="https://radspeed.com.au/impressions"', response.text)


if __name__ == "__main__":
    unittest.main()
