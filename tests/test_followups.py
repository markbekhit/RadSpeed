"""Regression tests for local priors and radiologist-owned follow-ups."""
from __future__ import annotations

import os
import tempfile
import unittest

from web.audit import (
    init_audit_db,
    list_prior_reports_for_patient,
    save_report_version,
)
from web.auth_oauth import get_or_create_user, init_db
from web.followups import (
    create_followup,
    init_followup_db,
    list_followups,
    suggest_followups,
    update_followup,
)


class FollowupRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("VOXRAD_DB_PATH")
        os.environ["VOXRAD_DB_PATH"] = os.path.join(self.temp.name, "users.db")
        init_db()
        init_audit_db()
        init_followup_db()
        self.user = get_or_create_user("reader@example.test", "Test Reader", "test")
        self.other = get_or_create_user("other@example.test", "Other Reader", "test")

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("VOXRAD_DB_PATH", None)
        else:
            os.environ["VOXRAD_DB_PATH"] = self.old_db
        self.temp.cleanup()

    def test_suggestions_require_explicit_recommendation_language(self):
        suggestions = suggest_followups(
            "Stable pulmonary nodule. Follow-up CT chest in 12 months is recommended. "
            "No further follow-up is required for the simple renal cyst."
        )
        self.assertEqual(len(suggestions), 1)
        self.assertIn("12 months", suggestions[0]["recommendation"])

    def test_followups_are_owned_and_can_be_completed(self):
        saved = create_followup(
            user_id=self.user["id"],
            patient_id="SYNTH-MRN-1",
            accession="SYNTH-ACC-1",
            recommendation="Follow-up CT chest in 12 months.",
            due_date="2027-01-20",
        )
        self.assertEqual(len(list_followups(self.user["id"])), 1)
        self.assertEqual(list_followups(self.other["id"]), [])
        self.assertIsNone(update_followup(saved["id"], self.other["id"], status="completed"))
        completed = update_followup(saved["id"], self.user["id"], status="completed")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(list_followups(self.user["id"]), [])

    def test_priors_return_latest_signed_version_per_accession(self):
        first = save_report_version(
            user_id=self.user["id"], report_text="Original prior", status="final",
            patient_id="SYNTH-MRN-2", accession="PRIOR-1", modality="CT",
        )
        save_report_version(
            user_id=self.user["id"], report_text="Amended prior", status="amended",
            patient_id="SYNTH-MRN-2", accession="PRIOR-1", modality="CT",
            prior_version_id=first["id"], amendment_reason="Synthetic correction",
        )
        save_report_version(
            user_id=self.user["id"], report_text="Current report", status="final",
            patient_id="SYNTH-MRN-2", accession="CURRENT-1", modality="CT",
        )
        save_report_version(
            user_id=self.other["id"], report_text="Other reader report", status="final",
            patient_id="SYNTH-MRN-2", accession="OTHER-1", modality="CT",
        )

        priors = list_prior_reports_for_patient(
            user_id=self.user["id"], patient_id="SYNTH-MRN-2",
            exclude_accession="CURRENT-1",
        )
        self.assertEqual([report["accession"] for report in priors], ["PRIOR-1"])
        self.assertEqual(priors[0]["report_text"], "Amended prior")


if __name__ == "__main__":
    unittest.main()
