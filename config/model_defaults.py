"""Canonical model choices for RadSpeed.

Keep production and local defaults here so routine deployments cannot drift
back to an older model. Provider-specific streaming models are also named here
to make upgrades explicit and regression-testable.
"""

DEFAULT_TEXT_MODEL = "gpt-5.6-sol"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
ASSEMBLYAI_STREAMING_MODEL = "u3-rt-pro"
DEEPGRAM_STREAMING_MODEL = "nova-3-medical"
