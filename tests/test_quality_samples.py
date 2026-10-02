"""Opt-in quality retention and de-identification safeguards."""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class QualitySampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("VOXRAD_DB_PATH")
        os.environ["VOXRAD_DB_PATH"] = os.path.join(self.temp.name, "users.db")
        from web.auth_oauth import get_or_create_user, init_db
        from web.quality_samples import init_quality_samples

        init_db()
        init_quality_samples()
        self.user = get_or_create_user("quality@example.test", "Quality Reader", "test")

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("VOXRAD_DB_PATH", None)
        else:
            os.environ["VOXRAD_DB_PATH"] = self.old_db
        self.temp.cleanup()

    def test_setting_is_opt_in_and_persists(self):
        from web.auth_oauth import get_user_style, save_user_style

        style = get_user_style(self.user["id"])
        self.assertFalse(style["retain_deidentified_samples"])
        style["retain_deidentified_samples"] = True
        save_user_style(self.user["id"], style)
        self.assertTrue(get_user_style(self.user["id"])["retain_deidentified_samples"])

    def test_deidentification_removes_known_and_free_text_identifiers(self):
        from web.quality_samples import deidentify_text

        result = deidentify_text(
            "Name: Jane Citizen\nDOB: 14/03/1980\nMRN: ZX12345\n"
            "Email jane@example.test phone 0412 345 678. Citizen, Jane of "
            "14 Example Street. Medicare 1234 56789 1. Jane Citizen has a tear.",
            {"patient_name": "Jane Citizen", "patient_dob": "14/03/1980"},
        )

        self.assertNotIn("Jane Citizen", result)
        self.assertNotIn("14/03/1980", result)
        self.assertNotIn("ZX12345", result)
        self.assertNotIn("jane@example.test", result)
        self.assertNotIn("0412 345 678", result)
        self.assertNotIn("Citizen, Jane", result)
        self.assertNotIn("14 Example Street", result)
        self.assertNotIn("1234 56789 1", result)
        self.assertIn("tear", result)

    def test_deidentification_scrubs_context_ids_referrer_and_feedback(self):
        from web.quality_samples import deidentify_text

        context = {
            "patient_id": "MRN-88-991",
            "accession": "ACC 44 221",
            "referring_physician": "Dr Avery Example",
        }
        result = deidentify_text(
            "MRN88991 ACC-44-221. Dr Avery Example asks to fix the conclusion.",
            context,
        )
        self.assertNotIn("MRN88991", result)
        self.assertNotIn("ACC-44-221", result)
        self.assertNotIn("Avery", result)

    def test_disabled_retention_writes_nothing(self):
        from web.auth_oauth import _conn
        from web.quality_samples import save_quality_sample

        saved = save_quality_sample(
            user_id=self.user["id"], enabled=False, kind="format",
            source_text="Dictated tear.", output_text="Tear reported.",
        )
        with _conn() as db:
            count = db.execute("SELECT COUNT(*) FROM quality_samples").fetchone()[0]
        self.assertFalse(saved)
        self.assertEqual(count, 0)

    def test_opt_in_store_is_deidentified_and_withdrawal_deletes_it(self):
        from web.auth_oauth import _conn
        from web.quality_samples import delete_quality_samples, save_quality_sample, set_quality_retention

        set_quality_retention(self.user["id"], True)
        self.assertTrue(save_quality_sample(
            user_id=self.user["id"], enabled=True, kind="format",
            source_text="Jane Citizen has an arcuate ligament rupture.",
            output_text="Patient name: Jane Citizen\nArcuate ligament rupture.",
            patient_context={"patient_name": "Jane Citizen"},
            template_name="MRI_Knee.txt", model_name="synthetic-model",
        ))
        with _conn() as db:
            row = db.execute(
                "SELECT source_text, output_text FROM quality_samples WHERE user_id = ?",
                (self.user["id"],),
            ).fetchone()
        self.assertNotIn("Jane Citizen", row[0])
        self.assertNotIn("Jane Citizen", row[1])
        self.assertEqual(delete_quality_samples(self.user["id"]), 1)

    def test_rolling_retention_removes_samples_older_than_365_days(self):
        from web.auth_oauth import _conn
        from web.quality_samples import purge_quality_samples, save_quality_sample, set_quality_retention

        set_quality_retention(self.user["id"], True)
        save_quality_sample(
            user_id=self.user["id"], enabled=True, kind="format",
            source_text="Synthetic fracture.", output_text="Synthetic fracture.",
        )
        save_quality_sample(
            user_id=self.user["id"], enabled=True, kind="format",
            source_text="Current synthetic tear.", output_text="Current synthetic tear.",
        )
        with _conn() as db:
            oldest_id = db.execute(
                "SELECT MIN(id) FROM quality_samples"
            ).fetchone()[0]
            db.execute(
                "UPDATE quality_samples SET created_at = '2020-01-01 00:00:00' WHERE id = ?",
                (oldest_id,),
            )
            db.commit()
        self.assertEqual(purge_quality_samples(), 1)
        with _conn() as db:
            rows = db.execute("SELECT source_text FROM quality_samples").fetchall()
        self.assertEqual(rows, [("Current synthetic tear.",)])

    def test_withdrawal_deletes_only_that_users_samples(self):
        from web.auth_oauth import _conn, get_or_create_user
        from web.quality_samples import save_quality_sample, set_quality_retention

        other = get_or_create_user("other@example.test", "Other Reader", "test")
        for user in (self.user, other):
            set_quality_retention(user["id"], True)
            self.assertTrue(save_quality_sample(
                user_id=user["id"], enabled=True, kind="format",
                source_text="Synthetic tear.", output_text="Synthetic tear.",
            ))

        set_quality_retention(self.user["id"], False)
        with _conn() as db:
            remaining = db.execute(
                "SELECT user_id FROM quality_samples ORDER BY user_id"
            ).fetchall()
        self.assertEqual(remaining, [(other["id"],)])

    def test_settings_withdrawal_deletes_existing_samples(self):
        from web.app import SettingsRequest, api_save_settings
        from web.auth_oauth import get_user_style

        existing = get_user_style(self.user["id"])
        existing["retain_deidentified_samples"] = True
        with patch("web.app.oauth_enabled", return_value=True), patch(
            "web.app._is_admin", return_value=False
        ), patch("web.app.get_user_style", return_value=existing), patch(
            "web.app.save_user_style"
        ) as save, patch("web.app.set_quality_retention") as set_retention:
            api_save_settings(
                SettingsRequest(retain_deidentified_samples=False),
                user=self.user,
            )

        self.assertTrue(save.call_args.args[1]["retain_deidentified_samples"])
        set_retention.assert_called_once_with(self.user["id"], False)

    def test_stale_enabled_snapshot_cannot_write_after_withdrawal(self):
        from web.auth_oauth import _conn
        from web.quality_samples import save_quality_sample

        saved = save_quality_sample(
            user_id=self.user["id"], enabled=True, kind="format",
            source_text="Synthetic fracture.", output_text="Synthetic fracture.",
        )
        with _conn() as db:
            count = db.execute("SELECT COUNT(*) FROM quality_samples").fetchone()[0]
        self.assertFalse(saved)
        self.assertEqual(count, 0)

    def test_old_user_settings_schema_migrates_without_changing_preferences(self):
        from web.auth_oauth import get_user_style, init_db

        legacy_path = os.path.join(self.temp.name, "legacy.db")
        with sqlite3.connect(legacy_path) as db:
            db.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
                "name TEXT, provider TEXT, created_at TEXT, last_login TEXT)"
            )
            db.execute(
                "CREATE TABLE user_settings (user_id INTEGER PRIMARY KEY, "
                "style_spelling TEXT, style_numerals TEXT, style_measurement_unit TEXT, "
                "style_measurement_separator TEXT, style_decimal_precision INTEGER, "
                "style_laterality TEXT, style_impression_style TEXT, "
                "style_negation_phrasing TEXT, style_date_format TEXT, "
                "fhir_export_enabled INTEGER)"
            )
            db.execute(
                "INSERT INTO users (id, email, name, provider) VALUES (7, 'legacy@test', 'Legacy', 'test')"
            )
            db.execute(
                "INSERT INTO user_settings VALUES (7, 'american', 'arabic', 'mm', 'x', 2, "
                "'full', 'numbered', 'x_absent', 'yyyy_mm_dd', 1)"
            )
        os.environ["VOXRAD_DB_PATH"] = legacy_path
        init_db()
        style = get_user_style(7)
        self.assertEqual(style["spelling"], "american")
        self.assertEqual(style["numerals"], "arabic")
        self.assertTrue(style["fhir_export_enabled"])
        self.assertFalse(style["retain_deidentified_samples"])


if __name__ == "__main__":
    unittest.main()
