import logging
from typing import Optional

from config.config import config
from .base import StreamingSTTProvider

logger = logging.getLogger(__name__)


def resolve_streaming_provider_name() -> str:
    """Return the provider RadSpeed should use for the current configuration.

    ``auto`` (and the legacy empty value) prefers the strongest configured
    medical streaming service. Groq remains the segment-based fallback when no
    streaming key is available or when it is selected explicitly.
    """
    provider = (config.STREAMING_STT_PROVIDER or "auto").strip().lower()
    if provider == "auto":
        if config.ASSEMBLYAI_API_KEY:
            return "assemblyai"
        if config.DEEPGRAM_API_KEY:
            return "deepgram"
        return "groq"
    return provider


def get_streaming_provider() -> Optional[StreamingSTTProvider]:
    """Return the configured streaming STT provider instance, or None.

    Returns None when Groq fallback is selected or the required API key for an
    explicitly selected streaming provider is not configured.
    """
    provider = resolve_streaming_provider_name()

    if provider == "deepgram":
        if not config.DEEPGRAM_API_KEY:
            logger.warning("[factory] deepgram selected but DEEPGRAM_API_KEY not set")
            return None
        from .deepgram import DeepgramProvider
        return DeepgramProvider()

    if provider == "assemblyai":
        if not config.ASSEMBLYAI_API_KEY:
            logger.warning("[factory] assemblyai selected but ASSEMBLYAI_API_KEY not set")
            return None
        from .assemblyai import AssemblyAIProvider
        return AssemblyAIProvider()

    return None  # Groq uses the existing segment-based Whisper pipeline.
