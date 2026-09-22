"""Regression tests for the practice deployment profile.

Covers the privacy controls a radiology practice relies on: Australian data
residency checks, Deepgram regional endpoints, the Bedrock/Anthropic client
adapter, identifier minimisation, the AI disclosure line, retention purges,
idle session timeout, research-feature gating and the privacy headers.
Everything defaults off in the personal profile, so the first test pins that.
"""
from __future__ import annotations

import contextlib
import dataclasses
import os
import tempfile
import time
import types
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from config import practice


@contextlib.contextmanager
def profile_settings(**overrides):
    """Temporarily replace practice.settings with modified values."""
    original = practice.settings
    practice.settings = dataclasses.replace(original, **overrides)
    try:
        yield practice.settings
    finally:
        practice.settings = original


# ---------------------------------------------------------------------------
# Profile loading and residency validation
# ---------------------------------------------------------------------------

class ProfileLoadTests(unittest.TestCase):
    def test_personal_profile_keeps_existing_behaviour(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in list(os.environ):
                if key.startswith(("RADSPEED_", "DEEPGRAM_", "BEDROCK_")):
                    os.environ.pop(key)
            s = practice.load()
        self.assertEqual(s.profile, "personal")
        self.assertFalse(s.require_sso)
        self.assertFalse(s.residency_au)
        self.assertEqual(s.session_max_age_seconds, 30 * 24 * 3600)
        self.assertEqual(s.session_idle_timeout_seconds, 0)
        self.assertFalse(s.minimise_llm_identifiers)
        self.assertFalse(s.ai_disclosure_footer)
        self.assertTrue(s.research_features)
        self.assertEqual(s.retention_days, 0)
        self.assertEqual(s.deepgram_region, "global")
        self.assertFalse(s.deepgram_mip_opt_out)
        self.assertEqual(s.text_provider, "openai")

    def test_practice_profile_turns_every_control_on(self):
        with mock.patch.dict(os.environ, {"RADSPEED_PROFILE": "practice"}, clear=False):
            for key in list(os.environ):
                if key.startswith(("RADSPEED_", "DEEPGRAM_", "BEDROCK_")) and key != "RADSPEED_PROFILE":
                    os.environ.pop(key)
            s = practice.load()
        self.assertTrue(s.is_practice)
        self.assertTrue(s.residency_au)
        self.assertTrue(s.require_sso)
        self.assertEqual(s.session_max_age_seconds, 12 * 3600)
        self.assertEqual(s.session_idle_timeout_seconds, 1800)
        self.assertTrue(s.minimise_llm_identifiers)
        self.assertTrue(s.ai_disclosure_footer)
        self.assertFalse(s.research_features)
        self.assertEqual(s.retention_days, 30)
        self.assertEqual(s.outbox_retention_days, 14)
        self.assertEqual(s.deepgram_region, "au")
        self.assertTrue(s.deepgram_mip_opt_out)
        self.assertEqual(s.text_provider, "bedrock-anthropic")
        self.assertTrue(s.cookie_secure)

    def test_individual_variables_override_profile_defaults(self):
        env = {
            "RADSPEED_PROFILE": "practice",
            "RADSPEED_RESEARCH_FEATURES": "true",
            "RADSPEED_RETENTION_DAYS": "90",
            "RADSPEED_SESSION_IDLE_TIMEOUT_SECONDS": "0",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            s = practice.load()
        self.assertTrue(s.research_features)
        self.assertEqual(s.retention_days, 90)
        self.assertEqual(s.session_idle_timeout_seconds, 0)

    def test_host_allowed_under_au_residency(self):
        s = practice.PracticeSettings(data_residency="au", residency_allowed_hosts=("whisper.clinic.local",))
        self.assertTrue(s.host_allowed("wss://api.au.deepgram.com/v1/listen"))
        self.assertTrue(s.host_allowed("https://bedrock-runtime.ap-southeast-2.amazonaws.com/anthropic"))
        self.assertTrue(s.host_allowed("http://localhost:9000/v1"))
        self.assertTrue(s.host_allowed("http://whisper.clinic.local:8080/v1"))
        self.assertFalse(s.host_allowed("https://api.openai.com/v1"))
        self.assertFalse(s.host_allowed("https://api.groq.com/openai/v1"))
        self.assertFalse(s.host_allowed(None))

    def test_no_residency_allows_everything(self):
        s = practice.PracticeSettings()
        self.assertTrue(s.host_allowed("https://api.openai.com/v1"))

    def test_validate_reports_offshore_endpoints(self):
        s = practice.PracticeSettings(
            profile="practice", data_residency="au", require_sso=True,
            text_provider="openai", deepgram_region="global",
        )
        problems = practice.validate(
            s, oauth_configured=False, text_base_url="https://api.openai.com/v1",
            transcription_base_url="https://api.groq.com/openai/v1",
            streaming_provider="deepgram", deepgram_key=True,
        )
        joined = " ".join(problems)
        self.assertIn("OAuth", joined)
        self.assertIn("api.openai.com", joined)
        self.assertIn("DEEPGRAM_REGION", joined)

    def test_validate_passes_for_onshore_practice(self):
        s = practice.PracticeSettings(
            profile="practice", data_residency="au", require_sso=True,
            text_provider="bedrock-anthropic", bedrock_region="ap-southeast-2",
            deepgram_region="au",
        )
        problems = practice.validate(
            s, oauth_configured=True, text_base_url=None, transcription_base_url=None,
            streaming_provider="deepgram", deepgram_key=True,
        )
        self.assertEqual(problems, [])


# ---------------------------------------------------------------------------
# Deepgram regional endpoint
# ---------------------------------------------------------------------------

class DeepgramRegionTests(unittest.TestCase):
    def test_global_url_is_unchanged_by_default(self):
        from web.stt_providers.deepgram import build_listen_url
        with profile_settings(deepgram_region="global", deepgram_mip_opt_out=False):
            url = build_listen_url(16000, ["pneumothorax"])
        self.assertTrue(url.startswith("wss://api.deepgram.com/v1/listen?"))
        self.assertIn("model=nova-3-medical", url)
        self.assertIn("keyterm=pneumothorax", url)
        self.assertNotIn("mip_opt_out", url)

    def test_au_region_and_opt_out(self):
        from web.stt_providers.deepgram import build_listen_url
        with profile_settings(deepgram_region="au", deepgram_mip_opt_out=True):
            url = build_listen_url(16000, [])
        self.assertTrue(url.startswith("wss://api.au.deepgram.com/v1/listen?"))
        self.assertIn("mip_opt_out=true", url)

    def test_assemblyai_refused_under_au_residency(self):
        from config.config import config
        from web.stt_providers.factory import get_streaming_provider
        with profile_settings(data_residency="au"), \
                mock.patch.object(config, "STREAMING_STT_PROVIDER", "assemblyai", create=True), \
                mock.patch.object(config, "ASSEMBLYAI_API_KEY", "key", create=True):
            self.assertIsNone(get_streaming_provider())


# ---------------------------------------------------------------------------
# Bedrock / Anthropic chat adapter
# ---------------------------------------------------------------------------

class _FakeStream:
    def __init__(self, parts):
        self.text_stream = iter(parts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeMessages:
    def __init__(self):
        self.calls = []
        self.response = SimpleNamespace(
            id="msg_1", model="au.anthropic.claude-sonnet-5", stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            content=[SimpleNamespace(type="text", text="FINDINGS: clear.")],
        )

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStream(["FIND", "INGS"])


class BedrockClientTests(unittest.TestCase):
    def _client(self):
        from llm.text_client import BedrockAnthropicChatClient
        fake = SimpleNamespace(messages=_FakeMessages())
        client = BedrockAnthropicChatClient("key", "ap-southeast-2", anthropic_client=fake)
        return client, fake

    def test_factory_returns_openai_client_by_default(self):
        from openai import OpenAI
        from config.config import config
        from llm.text_client import get_text_client
        with profile_settings(text_provider="openai"), \
                mock.patch.object(config, "TEXT_API_KEY", "sk-test"), \
                mock.patch.object(config, "BASE_URL", "https://api.openai.com/v1"):
            self.assertIsInstance(get_text_client(), OpenAI)

    def test_factory_returns_bedrock_client_for_practice(self):
        from llm.text_client import BedrockAnthropicChatClient, get_text_client
        with profile_settings(text_provider="bedrock-anthropic", bedrock_region="ap-southeast-2"):
            client = get_text_client()
        self.assertIsInstance(client, BedrockAnthropicChatClient)
        self.assertEqual(
            client.base_url, "https://bedrock-runtime.ap-southeast-2.amazonaws.com/anthropic"
        )

    def test_messages_and_options_are_converted(self):
        client, fake = self._client()
        resp = client.chat.completions.create(
            model="au.anthropic.claude-sonnet-5",
            messages=[
                {"role": "system", "content": "You format reports."},
                {"role": "user", "content": "CT chest normal."},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        call = fake.messages.calls[0]
        self.assertEqual(call["system"], "You format reports.")
        self.assertEqual(call["messages"], [{"role": "user", "content": "CT chest normal."}])
        self.assertEqual(call["temperature"], 0.1)
        self.assertEqual(call["max_tokens"], 400)
        self.assertEqual(call["thinking"], {"type": "disabled"})
        self.assertEqual(resp.choices[0].message.content, "FINDINGS: clear.")
        self.assertEqual(resp.choices[0].finish_reason, "stop")
        self.assertIsNone(resp.choices[0].message.tool_calls)

    def test_tool_calls_round_trip(self):
        client, fake = self._client()
        fake.messages.response = SimpleNamespace(
            id="msg_2", model="m", stop_reason="tool_use", usage=None,
            content=[SimpleNamespace(type="tool_use", id="tu_1", name="select_template",
                                     input={"template": "CT_Chest"})],
        )
        resp = client.chat.completions.create(
            model="m",
            messages=[{"role": "user", "content": "pick"}],
            tools=[{"type": "function", "function": {
                "name": "select_template", "description": "d",
                "parameters": {"type": "object", "properties": {"template": {"type": "string"}}},
            }}],
            tool_choice={"type": "function", "function": {"name": "select_template"}},
        )
        call = fake.messages.calls[0]
        self.assertEqual(call["tools"][0]["name"], "select_template")
        self.assertIn("input_schema", call["tools"][0])
        self.assertEqual(call["tool_choice"], {"type": "tool", "name": "select_template"})
        tool_call = resp.choices[0].message.tool_calls[0]
        self.assertEqual(tool_call.function.name, "select_template")
        self.assertEqual(tool_call.function.arguments, '{"template": "CT_Chest"}')
        self.assertEqual(resp.choices[0].finish_reason, "tool_calls")

    def test_streaming_yields_openai_shaped_chunks(self):
        client, _ = self._client()
        chunks = list(client.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "x"}], stream=True,
        ))
        texts = [c.choices[0].delta.content for c in chunks if c.choices[0].delta.content]
        self.assertEqual(texts, ["FIND", "INGS"])
        self.assertEqual(chunks[-1].choices[0].finish_reason, "stop")

    def test_image_parts_become_base64_blocks(self):
        from llm.text_client import convert_messages
        system, messages = convert_messages([
            {"role": "user", "content": [
                {"type": "text", "text": "Read this worksheet."},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ]},
        ])
        self.assertEqual(system, "")
        blocks = messages[0]["content"]
        self.assertEqual(blocks[0], {"type": "text", "text": "Read this worksheet."})
        self.assertEqual(blocks[1]["type"], "image")
        self.assertEqual(blocks[1]["source"]["media_type"], "image/png")
        self.assertEqual(blocks[1]["source"]["data"], "AAAA")


# ---------------------------------------------------------------------------
# Identifier minimisation
# ---------------------------------------------------------------------------

class IdentifierMinimisationTests(unittest.TestCase):
    CTX = {
        "patient_name": "Jane Citizen",
        "patient_dob": (date.today() - timedelta(days=365 * 40 + 30)).strftime("%d/%m/%Y"),
        "patient_id": "MRN123456",
        "accession": "ACC-778899",
        "referring_physician": "Dr Example",
        "modality": "CT",
        "radiologist": "Dr Reader",
    }

    def test_block_carries_identifiers_when_minimisation_is_off(self):
        from llm.format import _build_patient_context_block
        with profile_settings(minimise_llm_identifiers=False):
            block = _build_patient_context_block(self.CTX)
        self.assertIn("Name: Jane Citizen", block)
        self.assertIn("MRN: MRN123456", block)

    def test_block_replaces_identifiers_and_adds_age(self):
        from llm.format import _build_patient_context_block
        with profile_settings(minimise_llm_identifiers=True):
            block = _build_patient_context_block(self.CTX)
        self.assertNotIn("Jane Citizen", block)
        self.assertNotIn("MRN123456", block)
        self.assertNotIn("ACC-778899", block)
        self.assertNotIn("Dr Example", block)
        self.assertIn("Name: [PATIENT NAME]", block)
        self.assertIn("Age: 40 years", block)
        self.assertIn("Modality: CT", block)
        self.assertIn("Radiologist: Dr Reader", block)

    def test_prior_report_is_scrubbed(self):
        from llm.format import _build_patient_context_block
        ctx = dict(self.CTX, comparison_report="Patient Jane Citizen, MRN123456. Lungs clear.")
        with profile_settings(minimise_llm_identifiers=True):
            block = _build_patient_context_block(ctx)
        self.assertNotIn("Jane Citizen", block)
        self.assertIn("[PATIENT NAME]", block)
        self.assertIn("Lungs clear.", block)

    def test_reinsert_restores_values(self):
        from llm.format import reinsert_identifiers
        text = "Patient: [PATIENT NAME] ([PATIENT MRN])\nAccession [ACCESSION]\nReferrer: [REFERRER]"
        out = reinsert_identifiers(text, self.CTX)
        self.assertEqual(
            out, "Patient: Jane Citizen (MRN123456)\nAccession ACC-778899\nReferrer: Dr Example"
        )

    def test_scrub_is_a_no_op_when_disabled(self):
        from llm.format import scrub_identifiers
        with profile_settings(minimise_llm_identifiers=False):
            self.assertEqual(scrub_identifiers("Jane Citizen", self.CTX), "Jane Citizen")


# ---------------------------------------------------------------------------
# AI disclosure line
# ---------------------------------------------------------------------------

class DisclosureTests(unittest.TestCase):
    def test_off_by_default(self):
        from llm.disclosure import append_disclosure
        with profile_settings(ai_disclosure_footer=False):
            self.assertEqual(append_disclosure("Report.", "Dr Reader"), "Report.")

    def test_appended_once(self):
        from llm.disclosure import append_disclosure
        with profile_settings(ai_disclosure_footer=True):
            once = append_disclosure("Report.", "Dr Reader", on=date(2026, 9, 22))
            twice = append_disclosure(once, "Dr Reader", on=date(2026, 9, 22))
        self.assertIn("AI-assisted draft (RadSpeed). Reviewed and signed by Dr Reader on 22 Sep 2026.", once)
        self.assertEqual(once, twice)


# ---------------------------------------------------------------------------
# Retention purge
# ---------------------------------------------------------------------------

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("VOXRAD_DB_PATH")
        os.environ["VOXRAD_DB_PATH"] = os.path.join(self.temp.name, "users.db")
        from web.audit import init_audit_db
        from web.auth_oauth import get_or_create_user, init_db
        from web.followups import init_followup_db
        init_db()
        init_audit_db()
        init_followup_db()
        self.user = get_or_create_user("reader@example.test", "Test Reader", "test")

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("VOXRAD_DB_PATH", None)
        else:
            os.environ["VOXRAD_DB_PATH"] = self.old_db
        self.temp.cleanup()

    def test_old_reports_are_scrubbed_but_chain_still_verifies(self):
        from web import retention
        from web.audit import _conn, get_report, log_event, save_report_version, verify_chain
        old = save_report_version(
            user_id=self.user["id"], report_text="Old report text", status="final",
            accession="A1", patient_id="MRN1", patient_name="Old Patient", patient_dob="1980-01-01",
        )
        new = save_report_version(
            user_id=self.user["id"], report_text="New report text", status="final",
            accession="A2", patient_id="MRN2", patient_name="New Patient",
        )
        log_event(user_id=self.user["id"], event_type="sign_off", report_id=old["id"], metadata={"v": 1})
        with _conn() as db:
            db.execute("UPDATE reports SET created_at = ? WHERE id = ?",
                       ("2020-01-01 00:00:00", old["id"]))
            db.commit()
        with profile_settings(retention_days=30, outbox_retention_days=0):
            result = retention.run_once()
        self.assertEqual(result["reports_scrubbed"], 1)
        scrubbed = get_report(old["id"])
        self.assertEqual(scrubbed["report_text"], retention.PURGED_TEXT)
        self.assertIsNone(scrubbed["patient_name"])
        self.assertIsNone(scrubbed["patient_id"])
        self.assertEqual(scrubbed["accession"], "A1")  # kept for audit lookups
        kept = get_report(new["id"])
        self.assertEqual(kept["report_text"], "New report text")
        self.assertTrue(verify_chain()["ok"])

    def test_disabled_retention_touches_nothing(self):
        from web import retention
        from web.audit import _conn, get_report, save_report_version
        row = save_report_version(user_id=self.user["id"], report_text="Keep", status="final")
        with _conn() as db:
            db.execute("UPDATE reports SET created_at = ? WHERE id = ?", ("2020-01-01 00:00:00", row["id"]))
            db.commit()
        with profile_settings(retention_days=0, outbox_retention_days=0):
            self.assertFalse(retention.enabled())
            result = retention.run_once()
        self.assertEqual(result["reports_scrubbed"], 0)
        self.assertEqual(get_report(row["id"])["report_text"], "Keep")

    def test_outbox_files_older_than_limit_are_removed(self):
        from web import retention
        outbox = os.path.join(self.temp.name, "hl7_outbox")
        os.makedirs(outbox)
        old_path = os.path.join(outbox, "old.hl7")
        new_path = os.path.join(outbox, "new.hl7")
        settings_path = os.path.join(outbox, "settings.json")
        for p in (old_path, new_path, settings_path):
            with open(p, "w") as fh:
                fh.write("x")
        stale = time.time() - 40 * 86400
        os.utime(old_path, (stale, stale))
        os.utime(settings_path, (stale, stale))
        removed = retention.purge_outboxes(14, directories=[outbox])
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))
        self.assertTrue(os.path.exists(settings_path))


# ---------------------------------------------------------------------------
# Session idle timeout
# ---------------------------------------------------------------------------

class IdleTimeoutTests(unittest.TestCase):
    def _request(self, session):
        return SimpleNamespace(session=session)

    def test_no_timeout_by_default(self):
        from web.auth_oauth import get_session_user
        session = {"user": {"id": 1}, "last_seen": int(time.time()) - 10_000}
        with profile_settings(session_idle_timeout_seconds=0):
            self.assertEqual(get_session_user(self._request(session)), {"id": 1})

    def test_idle_session_is_cleared(self):
        from web.auth_oauth import get_session_user
        session = {"user": {"id": 1}, "last_seen": int(time.time()) - 3600}
        with profile_settings(session_idle_timeout_seconds=1800):
            self.assertIsNone(get_session_user(self._request(session)))
        self.assertEqual(session, {})

    def test_active_session_is_refreshed(self):
        from web.auth_oauth import get_session_user
        session = {"user": {"id": 1}, "last_seen": int(time.time()) - 120}
        with profile_settings(session_idle_timeout_seconds=1800):
            self.assertEqual(get_session_user(self._request(session)), {"id": 1})
        self.assertGreaterEqual(session["last_seen"], int(time.time()) - 2)


# ---------------------------------------------------------------------------
# Web layer: research gating, privacy headers, strict origin
# ---------------------------------------------------------------------------

class WebProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from web.app import app
        cls.client = TestClient(app)

    def test_research_routes_answer_404_when_disabled(self):
        with profile_settings(research_features=False):
            self.assertEqual(self.client.get("/impressions").status_code, 404)
            self.assertEqual(
                self.client.post("/api/impressions/text", json={"findings": "x"}).status_code, 404
            )
        with profile_settings(research_features=True):
            self.assertEqual(self.client.get("/impressions").status_code, 200)

    def test_capabilities_expose_profile_and_are_not_cached(self):
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertIn("profile", body)
        self.assertIn("research_features", body)

    def test_public_pages_stay_cacheable(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers.get("cache-control"), "no-store")

    def test_strict_origin_rejects_cross_site_posts(self):
        with profile_settings(strict_origin=True):
            blocked = self.client.post(
                "/api/qa-check", json={"report_text": "x"},
                headers={"Origin": "https://evil.example"},
            )
            self.assertEqual(blocked.status_code, 403)
            same_site = self.client.post(
                "/api/qa-check", json={"report_text": "x"},
                headers={"Origin": "http://testserver"},
            )
            self.assertNotEqual(same_site.status_code, 403)
        with profile_settings(strict_origin=False):
            allowed = self.client.post(
                "/api/qa-check", json={"report_text": "x"},
                headers={"Origin": "https://evil.example"},
            )
            self.assertNotEqual(allowed.status_code, 403)


if __name__ == "__main__":
    unittest.main()
