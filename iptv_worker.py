import asyncio
import os
import aiohttp

from app import iptv

MAIN_URL = (os.getenv("IPTV_MAIN_URL") or os.getenv("MINIAPP_URL") or "").rstrip("/")
TOKEN = (os.getenv("IPTV_WORKER_TOKEN") or os.getenv("INTERNAL_API_SECRET") or "").strip()

async def publish():
    if not MAIN_URL or not TOKEN:
        raise RuntimeError("IPTV_MAIN_URL/MINIAPP_URL and IPTV_WORKER_TOKEN are required")
    await asyncio.gather(
        iptv.refresh_channels(force=True),
        iptv.refresh_epg(force=True),
    )
    payload = {"state": iptv.public_state()}
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
    while True:
        try:
            await publish()
        except Exception as exc:
            print(f"IPTV worker error: {exc!r}", flush=True)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
