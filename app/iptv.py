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
    ("AM", "https://iptv-org.github.io/iptv/languages/hy.m3u"),
    ("AM", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_armenia.m3u8"),
    ("RU", "https://iptv-org.github.io/iptv/countries/ru.m3u"),
    ("RU", "https://raw.githubusercontent.com/substanc1/iptv-russia/main/streams/ru.m3u"),
    ("RU", "https://ngrch.github.io/iptv/ru.m3u"),
    ("RU", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8"),
]
MAX_STREAMS = 800
REFRESH_SECONDS = 900
PROBE_CONCURRENCY = 40

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


def _normalize_name(name: str) -> str:
    s = re.sub(r"\s+", " ", str(name or "").strip().lower())
    s = re.sub(r"\b(hd|full hd|fhd|uhd|4k|1080p|720p|480p|live|tv)\b", " ", s)
    s = re.sub(r"[^\w\u0400-\u04FF\u0530-\u058F]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _channel_key(item: dict) -> str:
    tvg_id = str(item.get("tvg_id") or "").strip().lower()
    if tvg_id:
        return "id:" + tvg_id
    return (str(item.get("country") or "") + ":" + _normalize_name(item.get("name") or "")).strip(":")


def _looks_junk(item: dict) -> bool:
    name = str(item.get("name") or "").strip().lower()
    url = str(item.get("url") or "").strip().lower()
    group = str(item.get("group") or "").strip().lower()
    if not name or len(name) < 2:
        return True
    bad_name = (
        "test", "demo", "sample", "backup", "reserve", "technical",
        "служеб", "тест", "резерв", "radio", "радио"
    )
    if any(x in name for x in bad_name):
        return True
    if group in {"radio", "radios", "радио"}:
        return True
    if not url.startswith(("http://", "https://")):
        return True
    return False


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
            key_src = _channel_key(row)
            if not key_src:
                pending = None
                continue
            row["id"] = hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:16]
            if not _looks_junk(row):
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
                seen_urls = set()
                unique = []
                for item in candidates:
                    url = item.get("url")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    unique.append(item)
                    if len(unique) >= MAX_STREAMS:
                        break
                sem = asyncio.Semaphore(PROBE_CONCURRENCY)
                checked = await asyncio.gather(*[_probe(session, item, sem) for item in unique])
            grouped = {}
            for item in checked:
                grouped.setdefault(item["id"], []).append(item)

            channels = {}
            for cid, rows in grouped.items():
                rows.sort(key=lambda x: (
                    x.get("status") != "ONLINE",
                    0 if str(x.get("logo") or "").startswith("http") else 1,
                    int(x.get("latency_ms") or 999999),
                ))
                primary = dict(rows[0])

                online_rows = []
                seen_streams = set()
                for x in rows:
                    if x.get("status") != "ONLINE":
                        continue
                    url = x.get("url")
                    if not url or url in seen_streams:
                        continue
                    seen_streams.add(url)
                    online_rows.append(x)

                primary["backups"] = [x["url"] for x in online_rows[1:] if x.get("url") != primary.get("url")]
                primary["backup_count"] = len(primary["backups"])
                primary["candidate_count"] = len(rows)
                primary["duplicate_count"] = max(0, len(rows) - 1)
                primary["sources"] = sorted({str(x.get("source") or "") for x in rows if x.get("source")})
                primary["normalized_name"] = _normalize_name(primary.get("name") or "")
                primary["last_checked"] = int(time.time())
                channels[cid] = primary

            online = sum(1 for x in channels.values() if x.get("status") == "ONLINE")
            _state["channels"] = channels
            _state["last_refresh"] = int(time.time())
            _state["stats"] = {
                "total": len(channels),
                "online": online,
                "offline": len(channels) - online,
                "source_count": len(SOURCE_URLS),
                "candidate_streams": len(checked),
                "duplicates_removed": max(0, len(checked) - len(channels)),
                "with_backups": sum(1 for x in channels.values() if int(x.get("backup_count") or 0) > 0),
            }
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


async def api_diagnostics(request):
    state = public_state()
    rows = state.get("channels") or []
    problem = [
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "country": x.get("country"),
            "status": x.get("status"),
            "latency_ms": x.get("latency_ms"),
            "backup_count": x.get("backup_count", 0),
            "candidate_count": x.get("candidate_count", 1),
            "duplicate_count": x.get("duplicate_count", 0),
            "source_count": len(x.get("sources") or []),
            "error": x.get("error", ""),
        }
        for x in rows
        if x.get("status") != "ONLINE" or int(x.get("backup_count") or 0) == 0
    ][:300]
    return web.json_response({
        "ok": True,
        "stats": state.get("stats") or {},
        "last_refresh": state.get("last_refresh"),
        "running": state.get("running"),
        "problem_channels": problem,
    }, headers={"Cache-Control": "no-store"})


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

    urls = []
    for url in [item.get("url"), *(item.get("backups") or [])]:
        if url and url not in urls:
            urls.append(url)

    timeout = aiohttp.ClientTimeout(total=15, connect=6, sock_read=8)
    last_error = ""
    async with aiohttp.ClientSession(headers={"User-Agent": "IPTV-Player/1.0"}) as session:
        for idx, url in enumerate(urls):
            try:
                async with session.get(url, timeout=timeout, allow_redirects=True) as r:
                    ctype = (r.headers.get("content-type") or "").lower()
                    final_url = str(r.url)
                    if r.status >= 400:
                        last_error = f"HTTP {r.status}"
                        continue

                    is_hls = "mpegurl" in ctype or urlparse(final_url).path.lower().endswith(".m3u8")
                    if is_hls:
                        body = await r.read()
                        if b"#EXTM3U" not in body[:4096] and "mpegurl" not in ctype:
                            last_error = "invalid HLS manifest"
                            continue

                        if idx > 0:
                            old_primary = item.get("url")
                            item["url"] = url
                            item["backups"] = [x for x in urls if x != url]
                            item["backup_count"] = len(item["backups"])
                            item["last_failover"] = int(time.time())
                            item["failed_url"] = old_primary or ""

                        text = body.decode("utf-8", "ignore")
                        return web.Response(
                            text=_rewrite_hls(text, final_url),
                            content_type="application/vnd.apple.mpegurl",
                            headers={
                                "Cache-Control": "no-store",
                                "X-IPTV-Source": "backup" if idx > 0 else "primary",
                                "X-IPTV-Backups": str(len(item.get("backups") or [])),
                            },
                        )

                    if ctype.startswith(("video/", "audio/")) or "octet-stream" in ctype:
                        if idx > 0:
                            old_primary = item.get("url")
                            item["url"] = url
                            item["backups"] = [x for x in urls if x != url]
                            item["backup_count"] = len(item["backups"])
                            item["last_failover"] = int(time.time())
                            item["failed_url"] = old_primary or ""
                        raise web.HTTPTemporaryRedirect(url)

                    last_error = f"unsupported content-type {ctype}"
            except web.HTTPException:
                raise
            except Exception as exc:
                last_error = str(exc)[:160]
                continue

    raise web.HTTPBadGateway(text="All channel streams failed: " + last_error)


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
    app.router.add_get("/api/iptv/diagnostics", api_diagnostics)
    app.router.add_post("/api/iptv/refresh", api_refresh)
    app.router.add_get("/api/iptv/play", api_play)
    app.router.add_get("/api/iptv/proxy", api_proxy)
    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
