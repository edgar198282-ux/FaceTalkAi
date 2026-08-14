import os
import asyncio
import tempfile
from openai import AsyncOpenAI
from .config import (
    OPENAI_API_KEY, TEXT_MODEL, TRANSCRIBE_MODEL, TTS_MODEL, TTS_VOICE,
    GROQ_API_KEY, GROQ_TEXT_MODEL, GROQ_TRANSCRIBE_MODEL,
    FREE_TTS_ENABLED, FREE_TTS_VOICE_RU, FREE_TTS_VOICE_HY, FREE_TTS_VOICE_EN,
)
from .roles import ROLES

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=35.0) if OPENAI_API_KEY else None
groq_client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=35.0,
) if GROQ_API_KEY else None

def _usage(r, provider, model):
    u = getattr(r, "usage", None)
    return {
        "input_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        "provider": provider,
        "model": model,
    }

async def _chat_with(client, provider, models, messages):
    last = None
    for model in models:
        if not model:
            continue
        try:
            r = await asyncio.wait_for(
                client.chat.completions.create(model=model, messages=messages),
                timeout=35,
            )
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text, _usage(r, provider, model)
        except Exception as e:
            last = e
    raise RuntimeError(f"{provider} не ответил: {str(last)[:220]}")

async def chat(role_key, history, user_text):
    system = (
        ROLES.get(role_key, ROLES["friend"])[1]
        + "\nВсегда отвечай на языке пользователя. "
          "Отвечай естественно и кратко, удобно для живого разговора и озвучки."
    )
    messages = [{"role": "system", "content": system}] + history[-18:] + [
        {"role": "user", "content": user_text}
    ]

    errors = []

    # 1) Groq is primary/free-first
    if groq_client:
        try:
            return await _chat_with(
                groq_client,
                "groq",
                [GROQ_TEXT_MODEL, "openai/gpt-oss-20b"],
                messages,
            )
        except Exception as e:
            errors.append(str(e))

    # 2) OpenAI fallback
    if openai_client:
        try:
            models = []
            for m in (TEXT_MODEL, "gpt-5-mini", "gpt-4o-mini"):
                if m and m not in models:
                    models.append(m)
            return await _chat_with(openai_client, "openai", models, messages)
        except Exception as e:
            errors.append(str(e))

    if not GROQ_API_KEY and not OPENAI_API_KEY:
        raise RuntimeError("Не настроены GROQ_API_KEY и OPENAI_API_KEY")
    raise RuntimeError(" | ".join(errors)[-500:] or "AI недоступен")

async def transcribe(path):
    errors = []

    # Groq Whisper first
    if groq_client:
        try:
            with open(path, "rb") as f:
                r = await asyncio.wait_for(
                    groq_client.audio.transcriptions.create(
                        model=GROQ_TRANSCRIBE_MODEL,
                        file=f,
                        response_format="json",
                    ),
                    timeout=45,
                )
            text = (r.text or "").strip()
            if text:
                return text, "groq"
        except Exception as e:
            errors.append(f"Groq STT: {e}")

    # OpenAI fallback
    if openai_client:
        try:
            with open(path, "rb") as f:
                r = await asyncio.wait_for(
                    openai_client.audio.transcriptions.create(
                        model=TRANSCRIBE_MODEL,
                        file=f,
                    ),
                    timeout=45,
                )
            text = (r.text or "").strip()
            if text:
                return text, "openai"
        except Exception as e:
            errors.append(f"OpenAI STT: {e}")

    raise RuntimeError(" | ".join(errors)[-500:] or "Распознавание голоса недоступно")

def _detect_voice(text):
    # Armenian Unicode block
    if any("\u0530" <= ch <= "\u058F" for ch in text):
        return FREE_TTS_VOICE_HY
    # Cyrillic
    if any("\u0400" <= ch <= "\u04FF" for ch in text):
        return FREE_TTS_VOICE_RU
    return FREE_TTS_VOICE_EN

async def _edge_speech(text):
    if not FREE_TTS_ENABLED:
        return None
    try:
        import edge_tts
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        voice = _detect_voice(text)
        communicate = edge_tts.Communicate(text[:3500], voice=voice)
        await asyncio.wait_for(communicate.save(path), timeout=60)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path, "edge-tts"
        try:
            os.remove(path)
        except OSError:
            pass
    except Exception:
        try:
            if 'path' in locals() and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    return None

async def synthesize(text):
    # 1) Free TTS first
    free = await _edge_speech(text)
    if free:
        return free

    # 2) OpenAI TTS fallback
    if not openai_client:
        return None, None
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        r = await asyncio.wait_for(
            openai_client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text[:3500],
            ),
            timeout=45,
        )
        r.write_to_file(path)
        return path, "openai"
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        return None, None
