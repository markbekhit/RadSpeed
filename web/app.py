"""VoxRad Web Server — FastAPI application.

Launch via:
    python VoxRad.py --web [--host 0.0.0.0] [--port 8765]

Authentication: HTTP Basic Auth.
Password is read from the VOXRAD_WEB_PASSWORD environment variable
(default: "voxrad" — change before any non-localhost deployment).

WARNING: HTTP Basic Auth sends credentials in cleartext over plain HTTP.
Always run behind an HTTPS reverse proxy (e.g. nginx with TLS) in
production. See docs/web-server-setup.md.
"""

import asyncio
import base64
import difflib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from config.config import config
from config.settings import save_web_settings
from llm.dicom_sr_export import save_dicom_sr_report
from llm.fhir_export import save_fhir_report
from llm.hl7_export import save_hl7_report
from llm.hl7_import import archive_order, list_inbox
from llm.format import (
    apply_report_feedback,
    capitalize_after_colon,
    format_text,
    join_template,
    split_template,
    stream_format_text,
)
from llm.impressions import stream_impression
from web.auth_oauth import (
    exchange_google_code,
    exchange_microsoft_code,
    get_or_create_user,
    get_user_style,
    google_auth_url,
    google_enabled,
    init_db,
    microsoft_auth_url,
    microsoft_enabled,
    oauth_enabled,
    require_oauth_user,
    save_user_style,
    SESSION_SECRET_KEY,
    set_session_user,
    clear_session,
)
from web.audit import (
    get_report,
    init_audit_db,
    list_audit_events,
    list_reports_for_accession,
    list_reports_for_user,
    log_event,
    save_report_version,
    verify_chain,
)
from web.qa import run_qa_checks
from web.stt_providers import get_streaming_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="VoxRad Web", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY(), max_age=2592000)  # 30 days
# auto_error=False so we can return a redirect (not a 401) when OAuth is active
security = HTTPBasic(auto_error=False)

# Initialise user + audit databases on startup (noop if already created)
init_db()
init_audit_db()

_BASE_DIR = os.path.dirname(__file__)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
    name="static",
)
_jinja = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

# Cache-busting: use the current git commit hash (or a timestamp fallback)
# so browsers always load fresh JS/CSS after each deploy.
try:
    import subprocess
    _STATIC_VERSION = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=os.path.dirname(_BASE_DIR),
        stderr=subprocess.DEVNULL,
    ).decode().strip()
except Exception:
    _STATIC_VERSION = str(int(time.time()))

# ---------------------------------------------------------------------------
# Authentication — OAuth (primary) or HTTP Basic Auth (fallback)
# ---------------------------------------------------------------------------

_DEFAULT_WEB_PASSWORD = "voxrad"


def _verify_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> dict:
    """Unified auth dependency.

    OAuth mode  — reads the session; returns 307 → /login if not signed in.
    Basic Auth mode — validates the shared password; returns 401 if wrong.
    """
    if oauth_enabled():
        return require_oauth_user(request)

    # Basic Auth mode
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    expected = os.environ.get("VOXRAD_WEB_PASSWORD", _DEFAULT_WEB_PASSWORD)
    ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        expected.encode("utf-8"),
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return {"id": None, "email": credentials.username, "name": credentials.username}


def _get_username(user: dict) -> str:
    return user.get("name") or user.get("email") or "user"


def _user_style(user: dict) -> Optional[dict]:
    """Return per-user style dict in OAuth mode; None (→ global config) in Basic Auth mode."""
    if oauth_enabled() and user.get("id") is not None:
        return get_user_style(user["id"])
    return None


def _user_fhir_enabled(user: dict) -> bool:
    """Per-user FHIR export toggle in OAuth mode; global config in Basic Auth mode."""
    if oauth_enabled() and user.get("id") is not None:
        return get_user_style(user["id"]).get("fhir_export_enabled", False)
    return config.fhir_export_enabled


PLACEHOLDER