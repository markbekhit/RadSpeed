"""Shared Playwright fixtures for a hermetic RadSpeed web server."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def radspeed_server(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("radspeed-e2e")
    home = runtime / "home"
    working = runtime / "working"
    home.mkdir()
    working.mkdir()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = runtime / "server.log"

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "VOXRAD_MOCK_MODE": "1",
            "VOXRAD_WEB_PASSWORD": "dev",
            "VOXRAD_WORKING_DIR": str(working),
            "VOXRAD_TEXT_API_KEY": "synthetic-test-key",
            "VOXRAD_TEXT_BASE_URL": f"{base_url}/mock/v1",
            "VOXRAD_TEXT_MODEL": "gpt-mock",
            "VOXRAD_TRANSCRIPTION_API_KEY": "synthetic-test-key",
            "VOXRAD_TRANSCRIPTION_BASE_URL": f"{base_url}/mock/v1",
            "VOXRAD_TRANSCRIPTION_MODEL": "whisper-mock",
        }
    )

    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "RadSpeed.py",
                "--web",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        deadline = time.monotonic() + 30
        last_error = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        yield base_url
                        break
            except Exception as exc:  # server still starting
                last_error = exc
                time.sleep(0.1)
        else:
            process.terminate()
            pytest.fail(f"RadSpeed E2E server did not start: {last_error}\n{log_path.read_text()}")

        if process.poll() is not None and not log.closed:
            pytest.fail(f"RadSpeed E2E server exited early:\n{log_path.read_text()}")

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="session")
def base_url(radspeed_server):
    return radspeed_server


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "http_credentials": {"username": "voxrad", "password": "dev"},
    }
