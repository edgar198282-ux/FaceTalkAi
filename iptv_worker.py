import asyncio
import os
import time
import aiohttp

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


async def publish():
    if not MAIN_URL or not TOKEN:
        raise RuntimeError("IPTV_MAIN_URL/MINIAPP_URL and IPTV_WORKER_TOKEN are required")
    await asyncio.gather(
        iptv.refresh_channels(force=True),
        iptv.refresh_epg(force=False),
    )
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
    interval = max(300, int(os.getenv("IPTV_WORKER_INTERVAL", str(iptv.REFRESH_SECONDS))))
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
