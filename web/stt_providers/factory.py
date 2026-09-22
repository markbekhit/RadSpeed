import logging
from typing import Optional

from config.config import config
from config import practice
from .base import StreamingSTTProvider

logger = logging.getLogger(__name__)


def resolve_streaming_provider_name() -> str:
    """Return the provider RadSpeed should use for the current configuration.

    ``auto`` (and the legacy empty value) prefers the strongest configured
    medical streaming service. Groq remains the segment-based fallback when no
    streaming key is available or when it is selected explicitly.
    """
    provider = (getattr(config, "STREAMING_STT_PROVIDER", None) or "auto").strip().lower()
    if provider == "auto":
        if getattr(config, "ASSEMBLYAI_API_KEY", None):
            return "assemblyai"
        if getattr(config, "DEEPGRAM_API_KEY", None):
            return "deepgram"
        return "groq"
    return provider


def get_streaming_provider() -> Optional[StreamingSTTProvider]:
    """Return the configured streaming STT provider instance, or None.

    Returns None when Groq fallback is selected or the required API key for an
    explicitly selected streaming provider is not configured.
    """
    provider = resolve_streaming_provider_name()

    if provider == "assemblyai" and practice.settings.residency_au:
        # AssemblyAI has no Australian region. Refuse rather than silently
        # sending audio offshore under a residency rule.
        logger.error("[factory] assemblyai is not permitted under RADSPEED_DATA_RESIDENCY=au")
        return None

    if provider == "deepgram":
        if not getattr(config, "DEEPGRAM_API_KEY", None):
            logger.warning("[factory] deepgram selected but DEEPGRAM_API_KEY not set")
            return None
        from .deepgram import DeepgramProvider
        return DeepgramProvider()

    if provider == "assemblyai":
        if not getattr(config, "ASSEMBLYAI_API_KEY", None):
            logger.warning("[factory] assemblyai selected but ASSEMBLYAI_API_KEY not set")
            return None
        from .assemblyai import AssemblyAIProvider
        return AssemblyAIProvider()

    return None  # Groq uses the existing segment-based Whisper pipeline.
