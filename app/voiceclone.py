import os, tempfile, aiohttp
from .config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL

BASE = "https://api.elevenlabs.io/v1"

async def create_clone(audio_bytes, filename="voice.webm", name="FaceTalk Voice"):
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY не настроен")
    form = aiohttp.FormData()
    form.add_field("name", name[:100])
    form.add_field("files", audio_bytes, filename=filename or "voice.webm", content_type="audio/webm")
    form.add_field("remove_background_noise", "false")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.post(f"{BASE}/voices/add", data=form, headers={"xi-api-key": ELEVENLABS_API_KEY}) as r:
            raw = await r.text()
            if r.status not in (200, 201):
                raise RuntimeError(f"ElevenLabs HTTP {r.status}: {raw[:240]}")
            data = await r.json()
    if not data.get("voice_id"):
        raise RuntimeError("ElevenLabs не вернул voice_id")
    return data

async def cloned_tts(text, voice_id):
    if not ELEVENLABS_API_KEY or not voice_id:
        return None
    headers={"xi-api-key":ELEVENLABS_API_KEY,"Content-Type":"application/json","Accept":"audio/mpeg"}
    payload={"text":text[:3500],"model_id":ELEVENLABS_MODEL}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
        async with session.post(f"{BASE}/text-to-speech/{voice_id}",
                                params={"output_format":"mp3_44100_128"},
                                json=payload,headers=headers) as r:
            data=await r.read()
            if r.status != 200:
                return None
    fd,path=tempfile.mkstemp(suffix=".mp3"); os.close(fd)
    with open(path,"wb") as f: f.write(data)
    return path
