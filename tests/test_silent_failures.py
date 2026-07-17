"""
Tests for the silent-failure surfacing paths (TODOS.md "Error diagnostics").

Covers the seven known silent failure modes: mic permission / silent input,
stale API keys (text model + Gemini), empty template dir, macOS AppleScript
permissions (Accessibility 1002 and macOS 15 Automation -1743), stale report
key, and corrupted settings.ini.

Heavy native deps (tkinter, sounddevice, pynput, lameenc, google.generativeai)
are stubbed so the modules under test import in a headless CI container.
"""
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import httpx
from openai import AuthenticationError


# ---------------------------------------------------------------------------
# Stub out native/GUI deps before importing the modules under test.
# setdefault so we never clobber stubs installed by other test modules.
# ---------------------------------------------------------------------------

def _stub_module(name, module=None):
    return sys.modules.setdefault(name, module if module is not None else MagicMock())


_stub_module("tkinter")
_stub_module("tkinter.ttk")
_stub_module("tkinter.filedialog")
_stub_module("tkinter.messagebox")
_stub_module("pynput")
_stub_module("pynput.keyboard")
_stub_module("lameenc")
_stub_module("google")
_stub_module("google.generativeai")

_sd_stub = types.ModuleType("sounddevice")


class _FakePortAudioError(Exception):
    pass


_sd_stub.PortAudioError = _FakePortAudioError
_sd_stub.query_devices = MagicMock(return_value=[])
_sd_stub.stop = MagicMock()
_sd_stub.InputStream = MagicMock()
_stub_module("sounddevice", _sd_stub)

# test_format.py installs minimal stubs for ui.utils / config.config that lack
# attributes the modules under test need. Backfill them instead of clobbering.
_ui_utils = sys.modules.get("ui.utils")
if _ui_utils is not None:
    for _attr in ("update_status", "draw_straight_line",
                  "stop_waveform_simulation", "start_waveform_simulation"):
        if not hasattr(_ui_utils, _attr):
            setattr(_ui_utils, _attr, lambda *a, **k: None)

import numpy as np  # noqa: E402

import audio.recorder as recorder  # noqa: E402
import audio.transcriber as transcriber  # noqa: E402
import llm.format as fmt  # noqa: E402
import llm.secure_paste as secure_paste  # noqa: E402
import utils.file_handling as file_handling  # noqa: E402
from config.config import config  # noqa: E402

# When test_format.py's config stub is active, backfill attributes these tests
# read/restore so getattr on the stub doesn't raise.
for _attr, _default in {
    "global_md_text_content": "",
    "template_dropdown": None,
    "current_encrypted_report": None,
    "current_report_encryption_key": None,
    "save_directory": None,
    "root": None,
    "secure_paste_shortcut": "ctrl+shift+v",
}.items():
    if not hasattr(config, _attr):
        setattr(config, _attr, _default)


def _auth_error():
    """Build a real openai.AuthenticationError (requires an httpx response)."""
    request = httpx.Request("POST", "http://test/v1/chat/completions")
    response = httpx.Response(401, request=request, json={"error": {"message": "bad key"}})
    return AuthenticationError("Invalid API key", response=response, body=None)


# ---------------------------------------------------------------------------
# 1. Mic permission / silent input
# ---------------------------------------------------------------------------

class TestSilentRecordingDetection(unittest.TestCase):
    def test_all_zero_audio_is_silent(self):
        self.assertTrue(recorder.is_silent_recording(np.zeros((44100, 1), dtype=np.float32)))

    def test_near_zero_noise_floor_is_silent(self):
        data = np.full((44100, 1), 5e-5, dtype=np.float32)
        self.assertTrue(recorder.is_silent_recording(data))

    def test_real_speech_amplitude_is_not_silent(self):
        data = np.zeros((44100, 1), dtype=np.float32)
        data[1000] = 0.2
        self.assertFalse(recorder.is_silent_recording(data))

    def test_empty_and_none_are_silent(self):
        self.assertTrue(recorder.is_silent_recording(np.array([])))
        self.assertTrue(recorder.is_silent_recording(None))

    def test_portaudio_error_surfaces_mic_message(self):
        messages = []
        recorder._recording_event.set()
        try:
            with patch.object(recorder, "update_status", messages.append), \
                 patch.object(recorder.sd, "InputStream",
                              side_effect=_FakePortAudioError("Device unavailable")):
                recorder.background_recording(device_index=0)
        finally:
            recorder._recording_event.clear()
        self.assertTrue(any("microphone permission" in m.lower() for m in messages),
                        f"no mic-permission message in {messages}")


# ---------------------------------------------------------------------------
# 2. Stale API keys — text model and Gemini
# ---------------------------------------------------------------------------

class TestTextModelAuthErrors(unittest.TestCase):
    def test_create_structured_report_surfaces_rejected_key(self):
        messages = []
        client = MagicMock()
        client.chat.completions.create.side_effect = _auth_error()
        with patch.object(fmt, "OpenAI", return_value=client), \
             patch.object(fmt, "update_status", messages.append):
            with self.assertRaises(fmt.TextModelAuthError):
                fmt._create_structured_report("transcript", "template body")
        self.assertIn(fmt._TEXT_KEY_REJECTED_MSG, messages)

    def test_select_template_surfaces_rejected_key(self):
        messages = []
        client = MagicMock()
        client.chat.completions.create.side_effect = _auth_error()
        with patch.object(fmt, "OpenAI", return_value=client), \
             patch.object(fmt, "update_status", messages.append), \
             patch.object(fmt, "_get_templates", return_value=["CT_Head.txt"]):
            with self.assertRaises(fmt.TextModelAuthError):
                fmt._select_template("ct head without contrast")
        self.assertIn(fmt._TEXT_KEY_REJECTED_MSG, messages)

    def test_format_text_returns_none_and_keeps_auth_status(self):
        """format_text must not overwrite the auth message or fall back to
        pseudo-successful unformatted output."""
        messages = []
        client = MagicMock()
        client.chat.completions.create.side_effect = _auth_error()
        old_template = config.global_md_text_content
        config.global_md_text_content = "some template"
        try:
            with patch.object(fmt, "OpenAI", return_value=client), \
                 patch.object(fmt, "update_status", messages.append):
                result = fmt.format_text("transcript")
        finally:
            config.global_md_text_content = old_template
        self.assertIsNone(result)
        self.assertEqual(messages[-1], fmt._TEXT_KEY_REJECTED_MSG)


class TestGeminiAuthDetection(unittest.TestCase):
    def test_invalid_key_messages_detected(self):
        for msg in (
            "400 API key not valid. Please pass a valid API key.",
            "API_KEY_INVALID",
            "403 Permission denied on resource",
            "401 UNAUTHENTICATED: Request had invalid authentication credentials",
        ):
            self.assertTrue(transcriber.is_gemini_auth_error(Exception(msg)), msg)

    def test_unrelated_errors_not_detected(self):
        for msg in ("500 Internal error", "Deadline exceeded", "429 Resource exhausted"):
            self.assertFalse(transcriber.is_gemini_auth_error(Exception(msg)), msg)


# ---------------------------------------------------------------------------
# 3. Empty template directory
# ---------------------------------------------------------------------------

class TestEmptyTemplateDir(unittest.TestCase):
    def test_load_templates_warns_when_dir_empty(self):
        messages = []
        status_stub = types.SimpleNamespace(update_status=messages.append)
        with tempfile.TemporaryDirectory() as tmp:
            old_save_dir, old_dropdown = config.save_directory, config.template_dropdown
            config.save_directory = tmp
            config.template_dropdown = None
            try:
                with patch.object(file_handling, "resource_path",
                                  side_effect=lambda p: os.path.join(tmp, "missing", p)), \
                     patch.dict(sys.modules, {"ui.utils": status_stub}):
                    file_handling.load_templates()
            finally:
                config.save_directory = old_save_dir
                config.template_dropdown = old_dropdown
        self.assertTrue(any("No report templates found" in m for m in messages),
                        f"no empty-template warning in {messages}")

    def test_load_templates_silent_when_templates_exist(self):
        messages = []
        status_stub = types.SimpleNamespace(update_status=messages.append)
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "templates"))
            with open(os.path.join(tmp, "templates", "CT_Head.txt"), "w") as f:
                f.write("template")
            old_save_dir, old_dropdown = config.save_directory, config.template_dropdown
            config.save_directory = tmp
            config.template_dropdown = None
            try:
                with patch.object(file_handling, "resource_path",
                                  side_effect=lambda p: os.path.join(tmp, "missing", p)), \
                     patch.dict(sys.modules, {"ui.utils": status_stub}):
                    file_handling.load_templates()
            finally:
                config.save_directory = old_save_dir
                config.template_dropdown = old_dropdown
        self.assertEqual(messages, [])


# ---------------------------------------------------------------------------
# 4. macOS AppleScript permissions (Accessibility 1002 / Automation -1743)
# ---------------------------------------------------------------------------

class TestAppleScriptErrorClassification(unittest.TestCase):
    def test_macos15_automation_error_detected(self):
        stderr = ("osascript: execution error: Not authorized to send Apple events "
                  "to System Events. (-1743)")
        self.assertEqual(secure_paste.classify_applescript_error(stderr), "automation")

    def test_accessibility_error_detected(self):
        stderr = ("osascript: execution error: System Events got an error: osascript "
                  "is not allowed to send keystrokes. (1002)")
        self.assertEqual(secure_paste.classify_applescript_error(stderr), "accessibility")

    def test_unrelated_error_not_classified(self):
        self.assertIsNone(secure_paste.classify_applescript_error(
            "syntax error: Expected end of line but found identifier. (-2741)"))
        self.assertIsNone(secure_paste.classify_applescript_error(""))
        self.assertIsNone(secure_paste.classify_applescript_error(None))

    def test_permission_messages_point_at_correct_pane(self):
        self.assertIn("Automation", secure_paste._APPLESCRIPT_PERMISSION_MSGS["automation"])
        self.assertIn("Accessibility", secure_paste._APPLESCRIPT_PERMISSION_MSGS["accessibility"])


# ---------------------------------------------------------------------------
# 6. Stale report key (secure paste)
# ---------------------------------------------------------------------------

class TestStaleReportKey(unittest.TestCase):
    def test_stale_report_key_surfaces_message(self):
        from cryptography.fernet import Fernet
        messages = []
        old_report = config.current_encrypted_report
        old_key = config.current_report_encryption_key
        config.current_encrypted_report = Fernet(Fernet.generate_key()).encrypt(b"report").decode()
        config.current_report_encryption_key = Fernet.generate_key().decode()  # wrong key
        try:
            with patch.object(secure_paste, "thread_safe_update_status", messages.append):
                secure_paste.secure_paste_report()
        finally:
            config.current_encrypted_report = old_report
            config.current_report_encryption_key = old_key
        self.assertTrue(any("stale" in m.lower() for m in messages),
                        f"no stale-key message in {messages}")

    def test_no_report_available_surfaces_message(self):
        messages = []
        old_report = config.current_encrypted_report
        config.current_encrypted_report = None
        try:
            with patch.object(secure_paste, "thread_safe_update_status", messages.append):
                secure_paste.secure_paste_report()
        finally:
            config.current_encrypted_report = old_report
        self.assertIn("No report available for secure paste.", messages)


# ---------------------------------------------------------------------------
# 7. Corrupted settings.ini
# ---------------------------------------------------------------------------

class TestCorruptedSettingsIni(unittest.TestCase):
    def test_get_save_directory_survives_corrupted_ini(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = os.path.join(tmp, ".voxrad")
            os.makedirs(config_dir)
            with open(os.path.join(config_dir, "settings.ini"), "w") as f:
                f.write("this is not\x00valid ini content\n[[[[")
            with patch.object(fmt.os.path, "expanduser", return_value=tmp):
                result = fmt._get_save_directory()
        self.assertEqual(result, config_dir)


if __name__ == "__main__":
    unittest.main()
