import os
import asyncio
import tempfile
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY, TEXT_MODEL, TRANSCRIBE_MODEL, TTS_MODEL, TTS_VOICE
from .roles import ROLES

client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=35.0) if OPENAI_API_KEY else None

async def chat(role_key: str, history: list, user_text: str) -> str:
    if not client:
        raise RuntimeError('OPENAI_API_KEY не настроен')
    system = ROLES.get(role_key, ROLES['friend'])[1] + '\nВсегда отвечай на языке пользователя. Отвечай естественно, без длинных вступлений, удобно для живого разговора и озвучки.'
    messages = [{'role': 'system', 'content': system}] + history[-18:] + [{'role': 'user', 'content': user_text}]
    models=[]
    for m in (TEXT_MODEL, 'gpt-5-mini', 'gpt-4o-mini'):
        if m and m not in models: models.append(m)
    last=None
    for model in models:
        try:
            r = await asyncio.wait_for(client.chat.completions.create(model=model, messages=messages), timeout=35)
            text=(r.choices[0].message.content or '').strip()
            if text: return text
        except Exception as e:
            last=e
    raise RuntimeError(f'OpenAI не ответил: {str(last)[:180]}')

async def transcribe(path: str) -> str:
    if not client: raise RuntimeError('OPENAI_API_KEY не настроен')
    with open(path, 'rb') as f:
        r = await asyncio.wait_for(client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=f), timeout=45)
    return (r.text or '').strip()

async def synthesize(text: str) -> str | None:
    if not client: return None
    fd, path = tempfile.mkstemp(suffix='.mp3'); os.close(fd)
    try:
        r = await asyncio.wait_for(client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=text[:3500]), timeout=45)
        r.write_to_file(path)
        return path
    except Exception:
        try: os.remove(path)
        except OSError: pass
        return None
