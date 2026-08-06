"""Regression coverage for production model choices and API compatibility."""

from __future__ import annotations

import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from config.model_defaults import (
    ASSEMBLYAI_STREAMING_MODEL,
    DEEPGRAM_STREAMING_MODEL,
    DEFAULT_TEXT_MODEL,
    DEFAULT_TRANSCRIPTION_MODEL,
)
from llm.model_compat import completion_options
from web.stt_providers.assemblyai import AssemblyAIProvider
from web.stt_providers.deepgram import DeepgramProvider


REPO_ROOT = Path(__file__).resolve().parents[1]


class ModelCompletionCompatibilityTests(unittest.TestCase):
    def test_gpt5_uses_modern_budget_and_default_temperature(self):
        options = completion_options(
            "gpt-5.6-sol",
            temperature=0.0,
            max_tokens=32,
            timeout=90,
        )
        self.assertNotIn("temperature", options)
        self.assertNotIn("max_tokens", options)
        self.assertEqual(options["max_completion_tokens"], 256)
        self.assertEqual(options["timeout"], 90)

    def test_legacy_openai_compatible_models_keep_legacy_parameters(self):
        options = completion_options(
            "gpt-4.1-mini",
            temperature=0.1,
            max_tokens=3000,
        )
        self.assertEqual(options["temperature"], 0.1)
        self.assertEqual(options["max_tokens"], 3000)
        self.assertNotIn("max_completion_tokens", options)


class ModelDefaultDurabilityTests(unittest.TestCase):
    def test_current_model_manifest(self):
        self.assertEqual(DEFAULT_TEXT_MODEL, "gpt-5.6-sol")
        self.assertEqual(DEFAULT_TRANSCRIPTION_MODEL, "whisper-large-v3-turbo")
        self.assertEqual(ASSEMBLYAI_STREAMING_MODEL, "u3-rt-pro")
        self.assertEqual(DEEPGRAM_STREAMING_MODEL, "nova-3-medical")

    def test_deployment_does_not_overwrite_operator_model_secret(self):
        workflow = (REPO_ROOT / ".github/workflows/aws-deploy.yml").read_text()
        self.assertNotIn("secrets set VOXRAD_TEXT_MODEL", workflow)
        self.assertNotIn("gpt-4.1-mini", workflow)

    def test_deployment_reclaims_unused_images_before_pull(self):
        workflow = (REPO_ROOT / ".github/workflows/aws-deploy.yml").read_text()
        prune = workflow.index("docker image prune -af")
        pull = workflow.index("docker compose pull")
        self.assertLess(prune, pull)


class StreamingProviderModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_assemblyai_uses_current_medical_model_and_turn_settings(self):
        websocket = AsyncMock()
        websocket.recv.return_value = '{"type":"Begin","id":"synthetic"}'
        with patch(
            "web.stt_providers.assemblyai.websockets.connect",
            new=AsyncMock(return_value=websocket),
        ) as connect:
            await AssemblyAIProvider().connect(
                "synthetic-key",
                sample_rate=16000,
                keywords=["pelvicaliectasis"],
            )

        url = connect.await_args.args[0]
        self.assertIn("speech_model=u3-rt-pro", url)
        self.assertIn("domain=medical-v1", url)
        self.assertIn("min_turn_silence=800", url)
        self.assertIn("max_turn_silence=3600", url)
        self.assertIn("keyterms_prompt=", url)

    async def test_deepgram_uses_latest_nova3_medical_with_keyterms(self):
        with patch(
            "web.stt_providers.deepgram.websockets.connect",
            new=AsyncMock(return_value=AsyncMock()),
        ) as connect:
            await DeepgramProvider().connect(
                "synthetic-key",
                sample_rate=16000,
                keywords=["pelvicaliectasis"],
            )

        url = connect.await_args.args[0]
        self.assertIn("model=nova-3-medical", url)
        self.assertIn("version=latest", url)
        self.assertIn("keyterm=pelvicaliectasis", url)


class StreamingProviderSelectionTests(unittest.TestCase):
    def _run_isolated(self, source: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_automatic_mode_prefers_assemblyai_medical_then_deepgram(self):
        self._run_isolated("""
from config.config import config
from web.stt_providers.factory import resolve_streaming_provider_name
config.STREAMING_STT_PROVIDER = "auto"
config.ASSEMBLYAI_API_KEY = "synthetic-assemblyai-key"
config.DEEPGRAM_API_KEY = "synthetic-deepgram-key"
assert resolve_streaming_provider_name() == "assemblyai"
config.ASSEMBLYAI_API_KEY = None
assert resolve_streaming_provider_name() == "deepgram"
config.DEEPGRAM_API_KEY = None
assert resolve_streaming_provider_name() == "groq"
""")

    def test_oauth_admin_provider_change_is_persisted(self):
        self._run_isolated("""
from unittest.mock import patch
from config.config import config
from web.app import SettingsRequest, api_save_settings
config.STREAMING_STT_PROVIDER = "groq"
request = SettingsRequest(streaming_stt_provider="assemblyai")
user = {"id": 1, "email": "synthetic@example.test", "name": "Synthetic"}
with patch("web.app.oauth_enabled", return_value=True), patch(
    "web.app._is_admin", return_value=True
), patch("web.app.get_user_style", return_value={}), patch(
    "web.app.save_user_style"
), patch("web.app.save_web_settings") as save:
    result = api_save_settings(request, user=user)
assert result["ok"] is True
assert config.STREAMING_STT_PROVIDER == "assemblyai"
save.assert_called_once_with()
""")

    def test_oauth_non_admin_cannot_receive_false_success_for_model_change(self):
        self._run_isolated("""
from unittest.mock import patch
from fastapi import HTTPException
from config.config import config
from web.app import SettingsRequest, api_save_settings
config.STREAMING_STT_PROVIDER = "groq"
request = SettingsRequest(streaming_stt_provider="assemblyai")
user = {"id": 2, "email": "synthetic2@example.test", "name": "Synthetic"}
with patch("web.app.oauth_enabled", return_value=True), patch(
    "web.app._is_admin", return_value=False
):
    try:
        api_save_settings(request, user=user)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("model change incorrectly reported success")
assert config.STREAMING_STT_PROVIDER == "groq"
""")

    def test_first_oauth_account_is_owner_when_no_admin_allowlist_exists(self):
        self._run_isolated("""
from unittest.mock import patch
from web.app import _is_admin
with patch("web.app.oauth_enabled", return_value=True), patch.dict(
    "os.environ", {"RADSPEED_ADMIN_EMAILS": ""}
):
    assert _is_admin({"id": 1, "email": "owner@example.test"}) is True
    assert _is_admin({"id": 2, "email": "user@example.test"}) is False
""")

    def test_web_settings_use_the_persistent_database_directory(self):
        self._run_isolated("""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from config.settings import get_default_config_path
with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "users.db"
    with patch.dict("os.environ", {"VOXRAD_DB_PATH": str(database)}, clear=False):
        assert Path(get_default_config_path()) == Path(directory) / "settings.ini"
""")


if __name__ == "__main__":
    unittest.main()
