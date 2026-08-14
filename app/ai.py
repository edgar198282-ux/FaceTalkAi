import os
import tempfile
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY, TEXT_MODEL, TRANSCRIBE_MODEL, TTS_MODEL, TTS_VOICE
from .roles import ROLES

client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

async def chat(role_key: str, history: list, user_text: str) -> str:
    if not client:
        return 'OpenAI API key не настроен. Добавьте OPENAI_API_KEY в .env.'
    system = ROLES.get(role_key, ROLES['friend'])[1] + '\nВсегда отвечай на языке пользователя. Ответ делай естественным и удобным для озвучки.'
    messages = [{'role': 'system', 'content': system}] + history[-18:] + [{'role': 'user', 'content': user_text}]
    r = await client.chat.completions.create(model=TEXT_MODEL, messages=messages)
    return (r.choices[0].message.content or '').strip()

async def transcribe(path: str) -> str:
    if not client:
        return ''
    with open(path, 'rb') as f:
        r = await client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=f)
    return r.text.strip()

async def synthesize(text: str) -> str | None:
    if not client:
        return None
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    r = await client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=text[:3500])
    r.write_to_file(path)
    return path
