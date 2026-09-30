import asyncio
import hashlib
import hmac
import os
import re
import time
from urllib.parse import quote, urljoin, urlparse

import aiohttp
from aiohttp import web

SOURCE_URLS = [
    ("AM", "https://iptv-org.github.io/iptv/countries/am.m3u"),
    ("RU", "https://iptv-org.github.io/iptv/countries/ru.m3u"),
]
MAX_STREAMS = 320
REFRESH_SECONDS = 900
PROBE_CONCURRENCY = 24

_state = {
    "channels": {},
    "last_refresh": 0,
    "running": False,
    "stats": {"total": 0, "online": 0, "offline": 0},
    "error": "",
}
_lock = asyncio.Lock()
_proxy_secret = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("FACETALK_BOT_TOKEN") or "iptv-player").encode()


def _attrs(line: str) -> dict[str, str]:
    return {k.lower(): v for k, v in re.findall(r'([\w-]+)="([^"]*)"', line)}


def _parse_m3u(text: str, country: str, source: str) -> list[dict]:
    out = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = _attrs(line)
            name = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "Channel")
            pending = {
                "name": name or "Channel",
                "group": attrs.get("group-title", "") or "Other",
                "tvg_id": attrs.get("tvg-id", ""),
                "logo": attrs.get("tvg-logo", ""),
                "country": country,
                "source": source,
            }
        elif not line.startswith("#") and pending and line.startswith(("http://", "https://")):
            row = dict(pending)
            row["url"] = line
            key_src = (row.get("tvg_id") or (country + ":" + row["name"])).lower()
            row["id"] = hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:16]
            out.append(row)
            pending = None
    return out


async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status >= 400:
                return ""
            return await r.text(errors="ignore")
    except Exception:
        return ""


async def _probe(session: aiohttp.ClientSession, item: dict, sem: asyncio.Semaphore) -> dict:
    started = time.perf_counter()
    ok = False
    code = 0
    error = ""
    try:
        async with sem:
            timeout = aiohttp.ClientTimeout(total=8, connect=4, sock_read=4)
            headers = {"Range": "bytes=0-2047", "User-Agent": "IPTV-Player/1.0"}
            async with session.get(item["url"], headers=headers, timeout=timeout, allow_redirects=True) as r:
                code = r.status
                ctype = (r.headers.get("content-type") or "").lower()
                chunk = await r.content.read(2048)
                is_hls = b"#EXTM3U" in chunk or "mpegurl" in ctype or urlparse(str(r.url)).path.lower().endswith(".m3u8")
                ok = r.status in (200, 206) and (is_hls or ctype.startswith(("video/", "audio/")) or len(chunk) >= 188)
                if not ok:
                    error = f"{r.status} {ctype}"[:120]
    except Exception as exc:
        error = str(exc)[:120]
    row = dict(item)
    row.update({
        "status": "ONLINE" if ok else "OFFLINE",
        "status_code": code,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "error": error,
    })
    return row


async def refresh_channels(force: bool = False):
    async with _lock:
        now = int(time.time())
        if not force and _state["channels"] and now - int(_state["last_refresh"] or 0) < REFRESH_SECONDS:
            return
        _state["running"] = True
        _state["error"] = ""
        try:
            connector = aiohttp.TCPConnector(limit=32, ssl=False)
            headers = {"User-Agent": "IPTV-Player/1.0"}
            async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                fetched = await asyncio.gather(*[_fetch_text(session, url) for _, url in SOURCE_URLS])
                candidates = []
                for (country, url), text in zip(SOURCE_URLS, fetched):
                    if "#EXTM3U" in text[:4096]:
                        candidates.extend(_parse_m3u(text, country, url))
                seen = set()
                unique = []
                for item in candidates:
                    if item["url"] in seen:
                        continue
                    seen.add(item["url"])
                    unique.append(item)
                    if len(unique) >= MAX_STREAMS:
                        break
                sem = asyncio.Semaphore(PROBE_CONCURRENCY)
                checked = await asyncio.gather(*[_probe(session, item, sem) for item in unique])
            channels = {item["id"]: item for item in checked}
            online = sum(1 for x in checked if x["status"] == "ONLINE")
            _state["channels"] = channels
            _state["last_refresh"] = int(time.time())
            _state["stats"] = {"total": len(checked), "online": online, "offline": len(checked) - online}
        except Exception as exc:
            _state["error"] = repr(exc)[:300]
        finally:
            _state["running"] = False


def public_state():
    rows = list(_state["channels"].values())
    rows.sort(key=lambda x: (x["status"] != "ONLINE", x.get("country", ""), x.get("group", ""), x.get("name", "")))
    return {
        "ok": not bool(_state["error"]),
        "running": _state["running"],
        "last_refresh": _state["last_refresh"],
        "stats": _state["stats"],
        "error": _state["error"],
        "channels": rows,
    }


def _token(url: str) -> str:
    return hmac.new(_proxy_secret, url.encode(), hashlib.sha256).hexdigest()


def _proxy_url(url: str) -> str:
    return "/api/iptv/proxy?u=" + quote(url, safe="") + "&s=" + _token(url)


def _rewrite_hls(text: str, base: str) -> str:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if line.startswith("#"):
            def repl(match):
                target = urljoin(base, match.group(1))
                return 'URI="' + _proxy_url(target) + '"'
            out.append(re.sub(r'URI="([^"]+)"', repl, raw))
        else:
            out.append(_proxy_url(urljoin(base, line)))
    return "\n".join(out) + "\n"


async def api_channels(request):
    if not _state["channels"]:
        await refresh_channels()
    return web.json_response(public_state(), headers={"Cache-Control": "no-store"})


async def api_refresh(request):
    if _state["running"]:
        return web.json_response({"ok": True, "running": True})
    asyncio.create_task(refresh_channels(force=True))
    return web.json_response({"ok": True, "running": True})


async def api_play(request):
    cid = request.query.get("id", "")
    item = _state["channels"].get(cid)
    if not item or item.get("status") != "ONLINE":
        raise web.HTTPNotFound(text="Channel unavailable")
    url = item["url"]
    timeout = aiohttp.ClientTimeout(total=15, connect=6, sock_read=8)
    async with aiohttp.ClientSession(headers={"User-Agent": "IPTV-Player/1.0"}) as session:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            body = await r.read()
            ctype = (r.headers.get("content-type") or "").lower()
            final_url = str(r.url)
    if b"#EXTM3U" in body[:4096] or "mpegurl" in ctype or urlparse(final_url).path.lower().endswith(".m3u8"):
        text = body.decode("utf-8", "ignore")
        return web.Response(text=_rewrite_hls(text, final_url), content_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-store"})
    return web.Response(body=body, content_type=ctype.split(";")[0] if ctype else "application/octet-stream")


async def api_proxy(request):
    url = request.query.get("u", "")
    sig = request.query.get("s", "")
    if not url.startswith(("http://", "https://")) or not hmac.compare_digest(sig, _token(url)):
        raise web.HTTPForbidden(text="Invalid stream token")
    timeout = aiohttp.ClientTimeout(total=20, connect=6, sock_read=12)
    async with aiohttp.ClientSession(headers={"User-Agent": "IPTV-Player/1.0"}) as session:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            body = await r.read()
            ctype = (r.headers.get("content-type") or "").lower()
            final_url = str(r.url)
            status = r.status
    if b"#EXTM3U" in body[:4096] or "mpegurl" in ctype or urlparse(final_url).path.lower().endswith(".m3u8"):
        return web.Response(text=_rewrite_hls(body.decode("utf-8", "ignore"), final_url), content_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-store"})
    return web.Response(body=body, status=status, content_type=ctype.split(";")[0] if ctype else "application/octet-stream", headers={"Cache-Control": "private, max-age=30"})


async def start_background(app):
    async def loop():
        await asyncio.sleep(2)
        while True:
            await refresh_channels(force=True)
            await asyncio.sleep(REFRESH_SECONDS)
    app["iptv_task"] = asyncio.create_task(loop())


async def stop_background(app):
    task = app.get("iptv_task")
    if task:
        task.cancel()


def install(app: web.Application):
    app.router.add_get("/api/iptv/channels", api_channels)
    app.router.add_post("/api/iptv/refresh", api_refresh)
    app.router.add_get("/api/iptv/play", api_play)
    app.router.add_get("/api/iptv/proxy", api_proxy)
    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
