import os
import asyncio
import tempfile
from openai import AsyncOpenAI
from .config import (
    TEXT_MODEL, TRANSCRIBE_MODEL, TTS_MODEL, TTS_VOICE,
    GROQ_TEXT_MODEL, GROQ_TRANSCRIBE_MODEL,
    FREE_TTS_ENABLED, FREE_TTS_VOICE_RU, FREE_TTS_VOICE_HY, FREE_TTS_VOICE_EN,
    TMP_DIR,
)
from .runtime_config import runtime_value
from .roles import ROLES

def _usage(r, provider, model):
    u = getattr(r, "usage", None)
    return {
        "input_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        "provider": provider,
        "model": model,
    }

async def _clients():
    groq_key = await runtime_value("GROQ_API_KEY")
    openai_key = await runtime_value("OPENAI_API_KEY")
    groq = AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1", timeout=35.0) if groq_key else None
    openai = AsyncOpenAI(api_key=openai_key, timeout=35.0) if openai_key else None
    return groq, openai

async def _chat_with(client, provider, models, messages):
    last = None
    for model in models:
        if not model:
            continue
        try:
            r = await asyncio.wait_for(client.chat.completions.create(model=model, messages=messages), timeout=35)
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text, _usage(r, provider, model)
        except Exception as e:
            last = e
    raise RuntimeError(f"{provider} не ответил: {str(last)[:220]}")

async def chat(role_key, history, user_text):
    system = (
        ROLES.get(role_key, ROLES["friend"])[1]
        + "\nВсегда отвечай на языке пользователя. Отвечай естественно и кратко, удобно для живого разговора и озвучки."
    )
    messages = [{"role": "system", "content": system}] + history[-18:] + [{"role": "user", "content": user_text}]
    groq_client, openai_client = await _clients()
    errors = []
    if groq_client:
        try:
            return await _chat_with(groq_client, "groq", [GROQ_TEXT_MODEL, "openai/gpt-oss-20b"], messages)
        except Exception as e:
            errors.append(str(e))
    if openai_client:
        try:
            models = []
            for m in (TEXT_MODEL, "gpt-5-mini", "gpt-4o-mini"):
                if m and m not in models:
                    models.append(m)
            return await _chat_with(openai_client, "openai", models, messages)
        except Exception as e:
            errors.append(str(e))
    if not groq_client and not openai_client:
        raise RuntimeError("Не настроены GROQ_API_KEY и OPENAI_API_KEY")
    raise RuntimeError(" | ".join(errors)[-500:] or "AI недоступен")

async def translate_text(text, target_lang, context=""):
    text = (text or "").strip()
    if not text:
        return ""
    target = {"ru":"Russian","hy":"Armenian","en":"English"}.get(str(target_lang or "").lower())
    if not target:
        raise RuntimeError("Unsupported translation language")
    groq_client, openai_client = await _clients()
    system = (
        f"You are a professional live film and TV dialogue translator. Translate ONLY the current dialogue into {target}. "
        "Keep names, numbers, jokes, tone and conversational style accurate. Do not summarize, explain, censor, add speaker labels, "
        "or repeat context. If the source is already in the target language, return it naturally unchanged."
    )
    messages = [{"role":"system","content":system}]
    if context:
        messages.append({"role":"system","content":"Previous dialogue context for continuity only; do not translate or repeat it:\n"+context[-1800:]})
    messages.append({"role":"user","content":"Current dialogue:\n"+text[:5000]})
    errors = []
    if groq_client:
        try:
            translated, _ = await _chat_with(groq_client, "groq", [GROQ_TEXT_MODEL, "openai/gpt-oss-20b"], messages)
            if translated:
                return translated
        except Exception as e:
            errors.append(str(e))
    if openai_client:
        try:
            translated, _ = await _chat_with(openai_client, "openai", [TEXT_MODEL, "gpt-5-mini", "gpt-4o-mini"], messages)
            if translated:
                return translated
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError(" | ".join(errors)[-500:] or "Перевод недоступен")


async def transcribe_dub(path):
    groq_client, openai_client = await _clients()
    errors = []
    if groq_client:
        for model in ("whisper-large-v3", GROQ_TRANSCRIBE_MODEL):
            if not model:
                continue
            try:
                with open(path, "rb") as f:
                    r = await asyncio.wait_for(
                        groq_client.audio.transcriptions.create(
                            model=model,
                            file=f,
                            response_format="json",
                            temperature=0,
                            prompt="Accurate movie and television dialogue. Preserve names, numbers and punctuation."
                        ),
                        timeout=50
                    )
                text = (r.text or "").strip()
                if text:
                    return text, "groq:"+model
            except Exception as e:
                errors.append(f"Groq STT {model}: {e}")
    if openai_client:
        try:
            with open(path, "rb") as f:
                r = await asyncio.wait_for(
                    openai_client.audio.transcriptions.create(
                        model=TRANSCRIBE_MODEL,
                        file=f,
                        prompt="Accurate movie and television dialogue. Preserve names, numbers and punctuation."
                    ),
                    timeout=50
                )
            text = (r.text or "").strip()
            if text:
                return text, "openai"
        except Exception as e:
            errors.append(f"OpenAI STT: {e}")
    raise RuntimeError(" | ".join(errors)[-500:] or "Распознавание голоса недоступно")


async def synthesize_dub(text, target_lang):
    text = (text or "").strip()
    if not text:
        return None, None
    voice = {
        "ru": FREE_TTS_VOICE_RU,
        "hy": FREE_TTS_VOICE_HY,
        "en": FREE_TTS_VOICE_EN,
    }.get(str(target_lang or "").lower(), _detect_voice(text))
    try:
        import edge_tts
        fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix=".mp3")
        os.close(fd)
        communicate = edge_tts.Communicate(text[:3500], voice=voice, rate="+4%")
        await asyncio.wait_for(communicate.save(path), timeout=45)
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
    return await synthesize(text)


async def transcribe(path):
    groq_client, openai_client = await _clients()
    errors = []
    if groq_client:
        try:
            with open(path, "rb") as f:
                r = await asyncio.wait_for(groq_client.audio.transcriptions.create(model=GROQ_TRANSCRIBE_MODEL, file=f, response_format="json"), timeout=45)
            text = (r.text or "").strip()
            if text:
                return text, "groq"
        except Exception as e:
            errors.append(f"Groq STT: {e}")
    if openai_client:
        try:
            with open(path, "rb") as f:
                r = await asyncio.wait_for(openai_client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=f), timeout=45)
            text = (r.text or "").strip()
            if text:
                return text, "openai"
        except Exception as e:
            errors.append(f"OpenAI STT: {e}")
    raise RuntimeError(" | ".join(errors)[-500:] or "Распознавание голоса недоступно")

def _detect_voice(text):
    if any("\u0530" <= ch <= "\u058F" for ch in text):
        return FREE_TTS_VOICE_HY
    if any("\u0400" <= ch <= "\u04FF" for ch in text):
        return FREE_TTS_VOICE_RU
    return FREE_TTS_VOICE_EN

async def _edge_speech(text):
    if not FREE_TTS_ENABLED:
        return None
    try:
        import edge_tts
        fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix=".mp3")
        os.close(fd)
        communicate = edge_tts.Communicate(text[:3500], voice=_detect_voice(text))
        await asyncio.wait_for(communicate.save(path), timeout=60)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path, "edge-tts"
        try: os.remove(path)
        except OSError: pass
    except Exception:
        try:
            if 'path' in locals() and os.path.exists(path): os.remove(path)
        except OSError: pass
    return None

async def synthesize(text):
    free = await _edge_speech(text)
    if free:
        return free
    openai_key = await runtime_value("OPENAI_API_KEY")
    if not openai_key:
        return None, None
    openai_client = AsyncOpenAI(api_key=openai_key, timeout=35.0)
    fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix=".mp3")
    os.close(fd)
    try:
        r = await asyncio.wait_for(openai_client.audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=text[:3500]), timeout=45)
        r.write_to_file(path)
        return path, "openai"
    except Exception:
        try: os.remove(path)
        except OSError: pass
        return None, None
