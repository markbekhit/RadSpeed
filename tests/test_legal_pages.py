"""The public privacy policy and terms pages, generated from docs/compliance."""

import unittest

from fastapi.testclient import TestClient

from web.app import app


class LegalPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_privacy_page_names_the_operator_and_contact(self):
        response = self.client.get("/privacy")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Clarity Insights Imaging Pty Ltd", response.text)
        self.assertIn("92 696 493 740", response.text)
        self.assertIn("hello@radspeed.com.au", response.text)
        self.assertIn("Australian Privacy Principles", response.text)
        self.assertIn("10 December", response.text)  # automated decision-making disclosure
        self.assertNotIn("Draft for review", response.text)

    def test_terms_page_states_clinical_responsibility(self):
        response = self.client.get("/terms")
        self.assertEqual(response.status_code, 200)
        self.assertIn("reporting radiologist must review every", response.text)
        self.assertIn("not a medical device", response.text)

    def test_legal_pages_are_public_and_in_the_sitemap(self):
        for path in ("/privacy", "/terms"):
            response = self.client.get(path)
            self.assertNotEqual(response.headers.get("cache-control"), "no-store", path)
        sitemap = self.client.get("/sitemap.xml").text
        self.assertIn("<loc>https://radspeed.com.au/privacy</loc>", sitemap)
        self.assertIn("<loc>https://radspeed.com.au/terms</loc>", sitemap)

    def test_landing_footer_links_to_legal_pages(self):
        landing = self.client.get("/").text
        self.assertIn('href="/privacy"', landing)
        self.assertIn('href="/terms"', landing)
