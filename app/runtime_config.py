import os
from .db import get_setting

RUNTIME_KEYS = (
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "DID_API_KEY",
    "LIVEPORTRAIT_URL",
    "MUSETALK_URL",
    "GPU_WORKER_TOKEN",
    "AVATAR_ENGINE",
    "ELEVENLABS_API_KEY",
    "OPENAI_ADMIN_KEY",
    "OPENAI_PROJECT_ID",
)

async def runtime_value(name: str, fallback: str = "") -> str:
    value = (await get_setting("runtime:" + name, "") or "").strip()
    if value:
        return value
    return (os.getenv(name, fallback) or "").strip()

def mask_secret(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "не добавлен"
    if len(value) <= 8:
        return "••••"
    return value[:3] + "••••••" + value[-4:]
