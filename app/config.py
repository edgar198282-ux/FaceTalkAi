import os
from dotenv import load_dotenv

load_dotenv()

def _int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

# Telegram / Mini App
# Railway values are sometimes pasted as FACETALK_BOT_TOKEN=123:ABC, with quotes,
# or with a leading "bot". Normalize those harmless wrappers and select the first
# syntactically valid Telegram token. An invalid FACETALK_BOT_TOKEN no longer makes
# the whole service crash before we can print a useful diagnostic.
def _clean_bot_token(value: str) -> str:
    v = (value or "").strip()
    # Remove matching surrounding quotes.
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
        v = v[1:-1].strip()
    # Accept accidental KEY=value paste.
    for key in ("FACETALK_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
        prefix = key + "="
        if v.upper().startswith(prefix):
            v = v[len(prefix):].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
                v = v[1:-1].strip()
            break
    # Accept Bot API URL / botTOKEN forms without changing a normal token.
    if "/bot" in v:
        v = v.rsplit("/bot", 1)[-1].split("/", 1)[0].strip()
    elif v.lower().startswith("bot") and ":" in v[3:]:
        v = v[3:].strip()
    return v

def _looks_like_bot_token(v: str) -> bool:
    if not v or ":" not in v:
        return False
    left, right = v.split(":", 1)
    return left.isdigit() and len(left) >= 5 and len(right) >= 20

_TOKEN_CANDIDATES = [
    ("FACETALK_BOT_TOKEN", _clean_bot_token(os.getenv("FACETALK_BOT_TOKEN", ""))),
    ("TELEGRAM_BOT_TOKEN", _clean_bot_token(os.getenv("TELEGRAM_BOT_TOKEN", ""))),
    ("BOT_TOKEN", _clean_bot_token(os.getenv("BOT_TOKEN", ""))),
]
FACETALK_BOT_TOKEN = _TOKEN_CANDIDATES[0][1]
TELEGRAM_BOT_TOKEN_SOURCE = next((name for name, value in _TOKEN_CANDIDATES if _looks_like_bot_token(value)), "")
TELEGRAM_BOT_TOKEN = next((value for _name, value in _TOKEN_CANDIDATES if _looks_like_bot_token(value)), "")
BOT_TOKEN = TELEGRAM_BOT_TOKEN
EXPECTED_BOT_USERNAME = os.getenv("EXPECTED_BOT_USERNAME", "FaceTalkID_bot").strip().lstrip("@")
MINIAPP_URL = os.getenv("MINIAPP_URL", "").rstrip("/")
PORT = _int("PORT", 8080)
ADMIN_ID = _int("ADMIN_ID", 0)

# Railway Volume persistence
RAILWAY_VOLUME_MOUNT_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
DATA_DIR = RAILWAY_VOLUME_MOUNT_PATH or os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "facetalk.db"))
MEDIA_DIR = os.path.join(DATA_DIR, "media")
TMP_DIR = os.path.join(DATA_DIR, "tmp")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

# OpenAI fallback
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

# Groq primary/free-first
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
GROQ_TRANSCRIBE_MODEL = os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo")

# Free TTS
FREE_TTS_ENABLED = os.getenv("FREE_TTS_ENABLED", "1").strip().lower() not in ("0","false","off","no")
FREE_TTS_VOICE_RU = os.getenv("FREE_TTS_VOICE_RU", "ru-RU-SvetlanaNeural")
FREE_TTS_VOICE_HY = os.getenv("FREE_TTS_VOICE_HY", "hy-AM-AnahitNeural")
FREE_TTS_VOICE_EN = os.getenv("FREE_TTS_VOICE_EN", "en-US-AvaNeural")

# Video
DID_API_KEY = os.getenv("DID_API_KEY", os.getenv("AVATAR_API_KEY", ""))
AVATAR_API_KEY = os.getenv("AVATAR_API_KEY", "")
# Free/self-hosted GPU pipeline. The main Railway app stays light; the heavy
# LivePortrait + MuseTalk worker can run on a GPU host and expose HTTP endpoints.
LIVEPORTRAIT_URL = os.getenv("LIVEPORTRAIT_URL", "").rstrip("/")
MUSETALK_URL = os.getenv("MUSETALK_URL", "").rstrip("/")
GPU_WORKER_TOKEN = os.getenv("GPU_WORKER_TOKEN", "")
AVATAR_ENGINE = os.getenv("AVATAR_ENGINE", "auto").strip().lower()  # auto | free_gpu | did
VIDEO_TIMEOUT = _int("VIDEO_TIMEOUT", 120)

# Voice cloning
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# Admin / costs
OPENAI_ADMIN_KEY = os.getenv("OPENAI_ADMIN_KEY", "")
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID", "")
DEFAULT_VIDEO_DAILY_LIMIT = max(0, _int("VIDEO_DAILY_LIMIT", 5))
VIDEO_LIMIT_DEFAULT = DEFAULT_VIDEO_DAILY_LIMIT

OPENAI_INPUT_USD_PER_1M = max(0.0, _float("OPENAI_INPUT_USD_PER_1M", 0.0))
OPENAI_OUTPUT_USD_PER_1M = max(0.0, _float("OPENAI_OUTPUT_USD_PER_1M", 0.0))
OPENAI_TTS_USD_PER_1M_CHARS = max(0.0, _float("OPENAI_TTS_USD_PER_1M_CHARS", 0.0))
DID_USD_PER_VIDEO = max(0.0, _float("DID_USD_PER_VIDEO", 0.0))
