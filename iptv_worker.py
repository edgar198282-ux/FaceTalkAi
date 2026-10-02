import asyncio
import json
import os
import time
import aiohttp
from openai import AsyncOpenAI

from app import iptv

MAIN_URL = (os.getenv("IPTV_MAIN_URL") or os.getenv("MINIAPP_URL") or "").rstrip("/")
TOKEN = (os.getenv("IPTV_WORKER_TOKEN") or os.getenv("INTERNAL_API_SECRET") or "").strip()

async def restore_health():
    if not MAIN_URL or not TOKEN:
        return
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            MAIN_URL + "/api/iptv/worker-bootstrap",
            headers={"X-IPTV-Worker-Token": TOKEN},
        ) as response:
            if response.status != 200:
                return
            data = await response.json()
            health = data.get("health") if isinstance(data, dict) else None
            if isinstance(health, dict):
                iptv._stream_health.clear()
                for key, value in list(health.items())[:5000]:
                    if isinstance(key, str) and isinstance(value, dict):
                        iptv._stream_health[key] = value
                print(f"Restored IPTV health: {len(iptv._stream_health)} streams", flush=True)


async def refresh_requested():
    if not MAIN_URL or not TOKEN:
        return False
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                MAIN_URL + "/api/iptv/worker-command",
                headers={"X-IPTV-Worker-Token": TOKEN},
            ) as response:
                if response.status != 200:
                    return False
                data = await response.json()
                return bool(isinstance(data, dict) and data.get("refresh"))
    except Exception:
        return False


async def _run_ai_audit():
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        return {"enabled": False, "provider": "groq", "error": "GROQ_API_KEY missing"}
    model = (os.getenv("GROQ_TEXT_MODEL") or "openai/gpt-oss-20b").strip()
    channels = list((iptv._state.get("channels") or {}).values())
    suspicious = []
    for ch in channels:
        if ch.get("status") != "ONLINE" or ch.get("unreliable") or not ch.get("logo"):
            suspicious.append({
                "id": ch.get("id"),
                "name": ch.get("name"),
                "country": ch.get("country"),
                "status": ch.get("status"),
                "uptime_pct": ch.get("uptime_pct"),
                "backup_count": ch.get("backup_count"),
                "has_logo": bool(ch.get("logo")),
                "sources": ch.get("sources") or [],
            })
        if len(suspicious) >= 120:
            break
    prompt = (
        "You audit an IPTV catalogue. Analyze only metadata, never invent availability. "
        "Return compact JSON with keys summary, suspicious_names, likely_duplicates, review_notes. "
        "Do not recommend removing a channel solely because of its name. Technical ONLINE/OFFLINE status is authoritative.\n\n"
        + json.dumps(suspicious, ensure_ascii=False, separators=(",", ":"))
    )
    client = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=35.0)
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": "You are a conservative IPTV catalogue auditor. Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
            ),
            timeout=40,
        )
        text = (response.choices[0].message.content or "").strip()
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"raw": text[:4000]}
        return {
            "enabled": True,
            "provider": "groq",
            "model": model,
            "checked": len(suspicious),
            "result": parsed,
            "at": int(time.time()),
        }
    except Exception as exc:
        return {"enabled": True, "provider": "groq", "model": model, "error": str(exc)[:300], "at": int(time.time())}


async def publish():
    if not MAIN_URL or not TOKEN:
        raise RuntimeError("IPTV_MAIN_URL/MINIAPP_URL and IPTV_WORKER_TOKEN are required")
    # The worker owns channel probing. EPG is refreshed by the main web service.
    await iptv.refresh_channels(force=True)
    ai_audit = await _run_ai_audit()
    iptv._state.setdefault("stats", {})["ai_audit"] = ai_audit
    payload = {"state": iptv.public_state(), "health": iptv._stream_health}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            MAIN_URL + "/api/iptv/worker-snapshot",
            json=payload,
            headers={"X-IPTV-Worker-Token": TOKEN},
        ) as response:
            text = await response.text()
            if response.status != 200:
                raise RuntimeError(f"snapshot publish failed: HTTP {response.status}: {text[:300]}")
            print(text, flush=True)

async def main():
    # Full AI channel analysis once every 24 hours by default. Manual refresh still runs immediately.
    interval = max(3600, int(os.getenv("IPTV_WORKER_INTERVAL", "86400")))
    try:
        await restore_health()
    except Exception as exc:
        print(f"IPTV health restore error: {exc!r}", flush=True)
    last_publish = 0.0
    while True:
        should_publish = not last_publish or (time.time() - last_publish >= interval)
        if not should_publish:
            should_publish = await refresh_requested()
        if should_publish:
            try:
                await publish()
                last_publish = time.time()
            except Exception as exc:
                print(f"IPTV worker error: {exc!r}", flush=True)
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
