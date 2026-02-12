import os
from dotenv import load_dotenv

load_dotenv()

# ─── Audio Settings ──────────────────────────────────────────
# Run: python -c "import sounddevice; print(sounddevice.query_devices())"
# to find your microphone index
MICROPHONE_INDEX = os.getenv("MICROPHONE_INDEX", "0")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # 'tiny' = faster, 'base' = more accurate
RECORD_DURATION = int(os.getenv("RECORD_DURATION", "7"))

# ─── TTS Settings ────────────────────────────────────────────
TTS_MODEL = os.getenv("TTS_MODEL", "quality")  # 'fast' (pocket-tts) or 'quality' (Chatterbox-Turbo)

# ─── OpenClaw Settings ───────────────────────────────────────
OPENCLAW_SESSION_ID = os.getenv("OPENCLAW_SESSION_ID", "agent:main:main")
