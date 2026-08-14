"""Talking-avatar adapter.

V1 intentionally keeps this provider-neutral. The bot already supports the full
conversation loop and voice replies. Connect HeyGen/D-ID/Tavus/other provider
here later without changing Telegram handlers.
"""
from .config import AVATAR_API_URL, AVATAR_API_KEY

async def create_video(photo_bytes: bytes, audio_path: str) -> str | None:
    # Provider-specific request goes here.
    # Return a local mp4 path when configured.
    return None
