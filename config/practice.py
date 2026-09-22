"""Deployment profile and privacy controls.

RadSpeed runs in one of two profiles, selected with ``RADSPEED_PROFILE``:

``personal`` (default)
    The behaviour RadSpeed has always had. Every control below is off unless
    its own environment variable turns it on, so existing deployments do not
    change.

``practice``
    Defaults tuned for an Australian radiology practice: patient data stays in
    Australia, single sign-on is mandatory, sessions expire, identifiers are
    kept out of the language-model prompt, signed reports carry an AI
    disclosure line, research features are off, and stored data is purged on
    a schedule. Any individual control can still be overridden by its own
    variable.

Every control is read once at import time and exposed as a module-level
``settings`` object so the rest of the app can check plain attributes.
``load()`` re-reads the environment (tests use it).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PROFILE_PERSONAL = "personal"
PROFILE_PRACTICE = "practice"

# Hosts that keep data inside Australia. A practice deployment with
# RADSPEED_DATA_RESIDENCY=au may only send audio or text to these hosts, or to
# hosts the operator adds with RADSPEED_RESIDENCY_ALLOWED_HOSTS (for example a
# self-hosted Whisper server inside the clinic network).
_AU_HOST_SUFFIXES = (
    "api.au.deepgram.com",
    "bedrock-runtime.ap-southeast-2.amazonaws.com",
    "bedrock-runtime.ap-southeast-4.amazonaws.com",
    "bedrock-mantle.ap-southeast-4.api.aws",
)
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        logger.warning("[practice] %s=%r is not a number; using %s", name, raw, default)
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


@dataclass
class PracticeSettings:
    profile: str = PROFILE_PERSONAL

    # Where patient data may be processed. "" = no restriction, "au" = Australia.
    data_residency: str = ""
    residency_allowed_hosts: tuple[str, ...] = ()

    # Login and sessions.
    require_sso: bool = False
    session_max_age_seconds: int = 30 * 24 * 3600
    session_idle_timeout_seconds: int = 0          # 0 = no idle timeout
    cookie_secure: Optional[bool] = None           # None = infer from base URL
    strict_origin: bool = False

    # What the language model is allowed to see.
    minimise_llm_identifiers: bool = False

    # Signed-report disclosure.
    ai_disclosure_footer: bool = False
    ai_disclosure_text: str = (
        "AI-assisted draft (RadSpeed). Reviewed and signed by {radiologist} on {date}."
    )

    # Features that generate clinical content beyond formatting the dictation.
    research_features: bool = True

    # Retention, in days. 0 = keep forever.
    retention_days: int = 0
    outbox_retention_days: int = 0
    retention_interval_seconds: int = 3600

    # Speech-to-text provider region controls.
    deepgram_region: str = "global"                # "global" | "au" | "eu"
    deepgram_mip_opt_out: bool = False

    # Text model provider: "openai" (any OpenAI-compatible endpoint) or
    # "bedrock-anthropic" (Claude on Amazon Bedrock, Anthropic Messages API).
    text_provider: str = "openai"
    bedrock_region: str = "ap-southeast-2"

    problems: list[str] = field(default_factory=list)

    @property
    def is_practice(self) -> bool:
        return self.profile == PROFILE_PRACTICE

    @property
    def residency_au(self) -> bool:
        return self.data_residency == "au"

    # -- residency helpers -------------------------------------------------

    def host_allowed(self, url_or_host: Optional[str]) -> bool:
        """Return True when data may be sent to *url_or_host* under the residency rule."""
        if not self.residency_au:
            return True
        if not url_or_host:
            return False
        host = url_or_host
        if "://" in url_or_host:
            host = urlparse(url_or_host).hostname or ""
        host = host.lower().strip()
        if not host:
            return False
        if host in _LOCAL_HOSTS:
            return True
        if any(host == s or host.endswith("." + s) for s in _AU_HOST_SUFFIXES):
            return True
        return any(host == s or host.endswith("." + s) for s in self.residency_allowed_hosts)


def load() -> PracticeSettings:
    """Read the environment and build the settings object."""
    profile = _env_str("RADSPEED_PROFILE", PROFILE_PERSONAL).lower()
    if profile not in (PROFILE_PERSONAL, PROFILE_PRACTICE):
        logger.warning("[practice] Unknown RADSPEED_PROFILE=%r; using personal", profile)
        profile = PROFILE_PERSONAL
    practice = profile == PROFILE_PRACTICE

    allowed = tuple(
        h.strip().lower()
        for h in os.environ.get("RADSPEED_RESIDENCY_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    )

    s = PracticeSettings(
        profile=profile,
        data_residency=_env_str("RADSPEED_DATA_RESIDENCY", "au" if practice else "").lower(),
        residency_allowed_hosts=allowed,
        require_sso=_env_bool("RADSPEED_REQUIRE_SSO", practice),
        session_max_age_seconds=_env_int(
            "RADSPEED_SESSION_MAX_AGE_SECONDS", 12 * 3600 if practice else 30 * 24 * 3600
        ),
        session_idle_timeout_seconds=_env_int(
            "RADSPEED_SESSION_IDLE_TIMEOUT_SECONDS", 1800 if practice else 0
        ),
        cookie_secure=(
            _env_bool("RADSPEED_COOKIE_SECURE", True)
            if os.environ.get("RADSPEED_COOKIE_SECURE", "").strip() or practice
            else None
        ),
        strict_origin=_env_bool("RADSPEED_STRICT_ORIGIN", practice),
        minimise_llm_identifiers=_env_bool("RADSPEED_MINIMISE_LLM_IDENTIFIERS", practice),
        ai_disclosure_footer=_env_bool("RADSPEED_AI_DISCLOSURE_FOOTER", practice),
        ai_disclosure_text=_env_str(
            "RADSPEED_AI_DISCLOSURE_TEXT",
            PracticeSettings.ai_disclosure_text,
        ),
        research_features=_env_bool("RADSPEED_RESEARCH_FEATURES", not practice),
        retention_days=_env_int("RADSPEED_RETENTION_DAYS", 30 if practice else 0),
        outbox_retention_days=_env_int("RADSPEED_OUTBOX_RETENTION_DAYS", 14 if practice else 0),
        retention_interval_seconds=_env_int("RADSPEED_RETENTION_INTERVAL_SECONDS", 3600),
        deepgram_region=_env_str("DEEPGRAM_REGION", "au" if practice else "global").lower(),
        deepgram_mip_opt_out=_env_bool("DEEPGRAM_MIP_OPT_OUT", practice),
        text_provider=_env_str(
            "RADSPEED_TEXT_PROVIDER", "bedrock-anthropic" if practice else "openai"
        ).lower(),
        bedrock_region=_env_str("BEDROCK_REGION", "ap-southeast-2").lower(),
    )
    if s.deepgram_region not in ("global", "au", "eu"):
        logger.warning("[practice] Unknown DEEPGRAM_REGION=%r; using global", s.deepgram_region)
        s.deepgram_region = "global"
    if s.text_provider not in ("openai", "bedrock-anthropic"):
        logger.warning("[practice] Unknown RADSPEED_TEXT_PROVIDER=%r; using openai", s.text_provider)
        s.text_provider = "openai"
    return s


def validate(s: PracticeSettings, *, oauth_configured: bool, text_base_url: Optional[str],
             transcription_base_url: Optional[str], streaming_provider: str,
             deepgram_key: bool) -> list[str]:
    """Return a list of configuration problems for the given settings.

    An empty list means the deployment satisfies its own profile. The web app
    refuses to start a practice deployment that reports problems, because a
    silent fallback (for example to a US endpoint) is exactly what the profile
    exists to prevent.
    """
    problems: list[str] = []
    if s.require_sso and not oauth_configured:
        problems.append(
            "RADSPEED_REQUIRE_SSO is on but no Google or Microsoft OAuth client is configured."
        )
    if s.residency_au:
        if s.text_provider == "openai" and not s.host_allowed(text_base_url):
            problems.append(
                f"Data residency is 'au' but the text model endpoint {text_base_url!r} is not an "
                "Australian host. Use RADSPEED_TEXT_PROVIDER=bedrock-anthropic or add the host to "
                "RADSPEED_RESIDENCY_ALLOWED_HOSTS."
            )
        if s.text_provider == "bedrock-anthropic" and not s.bedrock_region.startswith("ap-southeast-"):
            problems.append(
                f"Data residency is 'au' but BEDROCK_REGION={s.bedrock_region!r} is outside Australia."
            )
        if streaming_provider == "assemblyai":
            problems.append("Data residency is 'au' but AssemblyAI has no Australian region.")
        if streaming_provider == "deepgram" and s.deepgram_region != "au":
            problems.append("Data residency is 'au' but DEEPGRAM_REGION is not 'au'.")
        if streaming_provider == "groq" and not s.host_allowed(transcription_base_url):
            problems.append(
                f"Data residency is 'au' but the transcription endpoint {transcription_base_url!r} "
                "is not an Australian host. Configure Deepgram (DEEPGRAM_REGION=au) or a local "
                "Whisper server listed in RADSPEED_RESIDENCY_ALLOWED_HOSTS."
            )
        if streaming_provider == "deepgram" and not deepgram_key:
            problems.append("Deepgram is selected but DEEPGRAM_API_KEY is not set.")
    s.problems = problems
    return problems


settings = load()
