import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
TEXT_MODEL = os.getenv('OPENAI_TEXT_MODEL', 'gpt-5-mini')
TRANSCRIBE_MODEL = os.getenv('OPENAI_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe')
TTS_MODEL = os.getenv('OPENAI_TTS_MODEL', 'gpt-4o-mini-tts')
TTS_VOICE = os.getenv('OPENAI_TTS_VOICE', 'alloy')
DID_API_KEY = os.getenv('DID_API_KEY', os.getenv('AVATAR_API_KEY', ''))
MINIAPP_URL = os.getenv('MINIAPP_URL', '').rstrip('/')
PORT = int(os.getenv('PORT', '8080'))
DB_PATH = os.getenv('DB_PATH', 'data/facetalk.sqlite3')
VIDEO_TIMEOUT = int(os.getenv('VIDEO_TIMEOUT', '120'))
