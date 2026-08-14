import os
from dotenv import load_dotenv

load_dotenv()

def _int(name, default):
    try: return int(os.getenv(name, str(default)))
    except Exception: return default

def _float(name, default):
    try: return float(os.getenv(name, str(default)))
    except Exception: return default

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
TEXT_MODEL = os.getenv('OPENAI_TEXT_MODEL', 'gpt-5-mini')
TRANSCRIBE_MODEL = os.getenv('OPENAI_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe')
TTS_MODEL = os.getenv('OPENAI_TTS_MODEL', 'gpt-4o-mini-tts')
TTS_VOICE = os.getenv('OPENAI_TTS_VOICE', 'alloy')
DID_API_KEY = os.getenv('DID_API_KEY', os.getenv('AVATAR_API_KEY', ''))
MINIAPP_URL = os.getenv('MINIAPP_URL', '').rstrip('/')
PORT = _int('PORT', 8080)
DB_PATH = os.getenv('DB_PATH', 'data/facetalk.sqlite3')
VIDEO_TIMEOUT = _int('VIDEO_TIMEOUT', 120)
ADMIN_ID = _int('ADMIN_ID', 0)
DEFAULT_VIDEO_DAILY_LIMIT = max(0, _int('VIDEO_DAILY_LIMIT', 5))
# Optional estimates. Set your real provider prices in Railway if you want money estimates.
OPENAI_INPUT_USD_PER_1M = max(0.0, _float('OPENAI_INPUT_USD_PER_1M', 0.0))
OPENAI_OUTPUT_USD_PER_1M = max(0.0, _float('OPENAI_OUTPUT_USD_PER_1M', 0.0))
OPENAI_TTS_USD_PER_1M_CHARS = max(0.0, _float('OPENAI_TTS_USD_PER_1M_CHARS', 0.0))
DID_USD_PER_VIDEO = max(0.0, _float('DID_USD_PER_VIDEO', 0.0))

OPENAI_ADMIN_KEY = os.getenv('OPENAI_ADMIN_KEY', '')
OPENAI_PROJECT_ID = os.getenv('OPENAI_PROJECT_ID', '')
