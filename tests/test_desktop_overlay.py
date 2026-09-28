"""Regression coverage for the compact Windows reporting controller."""

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from web.app import app


ROOT = Path(__file__).resolve().parents[1]


class DesktopOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_workstation_contains_compact_recording_controls(self):
        response = self.client.get("/app?desktop=overlay", auth=("radiologist", "voxrad"))
        self.assertEqual(response.status_code, 200)
        for element_id in (
            "desktop-overlay-head",
            "recording-card",
            "btn-record",
            "btn-stop",
            "btn-overlay-copy",
            "btn-overlay-next",
            "btn-desktop-expand",
            "btn-desktop-settings",
            "btn-desktop-collapse",
        ):
            self.assertIn(f'id="{element_id}"', response.text)

    def test_desktop_launches_compact_and_keeps_settings_separate(self):
        source = (ROOT / "desktop/src-tauri/src/lib.rs").read_text()
        self.assertIn('app_url.set_query(Some("desktop=overlay"))', source)
        self.assertIn(".inner_size(520.0, 200.0)", source)
        self.assertIn(".always_on_top(true)", source)
        self.assertIn('get_webview_window("settings")', source)

    def test_remote_window_can_only_use_scoped_desktop_commands(self):
        capability = (
            ROOT / "desktop/src-tauri/capabilities/remote-report-copy.json"
        ).read_text()
        permissions = (
            ROOT / "desktop/src-tauri/permissions/report-copy.toml"
        ).read_text()
        self.assertIn('"allow-app-window-commands"', capability)
        self.assertIn('commands.allow = ["cmd_set_compact_mode", "cmd_show_settings"]', permissions)


if __name__ == "__main__":
    unittest.main()
