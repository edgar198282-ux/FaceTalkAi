import asyncio
import hashlib
import hmac
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

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
DATA_ROOT = os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or os.path.join(os.getcwd(), "data")
HEALTH_PATH = os.path.join(DATA_ROOT, "iptv_health.json")
SNAPSHOT_PATH = os.path.join(DATA_ROOT, "iptv_snapshot.json")
os.makedirs(DATA_ROOT, exist_ok=True)

def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, type(default)) else default
    except Exception:
        return default

def _save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

_stream_health = _load_json(HEALTH_PATH, {})

def _health_score(url: str) -> float:
    h = _stream_health.get(url) or {}
    total = int(h.get("successes") or 0) + int(h.get("failures") or 0)
    uptime = (int(h.get("successes") or 0) / total) if total else 0.5
    latency = max(1, int(h.get("avg_latency_ms") or 2500))
    consecutive = int(h.get("consecutive_failures") or 0)
    return round(uptime * 1000.0 - min(latency, 10000) / 25.0 - consecutive * 90.0, 3)

def _record_health(row: dict):
    url = str(row.get("url") or "")
    if not url:
        return
    now = int(time.time())
    h = dict(_stream_health.get(url) or {})
    ok = row.get("status") == "ONLINE"
    h["successes"] = int(h.get("successes") or 0) + (1 if ok else 0)
    h["failures"] = int(h.get("failures") or 0) + (0 if ok else 1)
    h["consecutive_failures"] = 0 if ok else int(h.get("consecutive_failures") or 0) + 1
    if ok:
        h["last_ok"] = now
    else:
        h["last_fail"] = now
        h["last_error"] = str(row.get("error") or "")[:160]
    latency = max(0, int(row.get("latency_ms") or 0))
    if latency:
        old = int(h.get("avg_latency_ms") or latency)
        h["avg_latency_ms"] = int(old * 0.8 + latency * 0.2)
    total = h["successes"] + h["failures"]
    h["uptime_pct"] = round((h["successes"] * 100.0 / total), 2) if total else 0.0
    h["updated_at"] = now
    _stream_health[url] = h
    h["score"] = _health_score(url)
    _stream_health[url] = h

EPG_URLS = [
    ("AM", "https://iptv-epg.org/files/epg-am.xml"),
    ("RU", "https://iptv-epg.org/files/epg-ru.xml"),
]
EPG_REFRESH_SECONDS = 3 * 60 * 60

_state = {
    "channels": {},
    "last_refresh": 0,
    "running": False,
    "stats": {"total": 0, "online": 0, "offline": 0},
    "error": "",
    "epg": {},
    "epg_names": {},
    "epg_last_refresh": 0,
    "epg_error": "",
}
_lock = asyncio.Lock()
_proxy_secret = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("FACETALK_BOT_TOKEN") or "iptv-player").encode()
_worker_control = {"refresh_requested_at": 0, "last_worker_snapshot": 0}


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


def _extinf_name(line: str, fallback: str = "Channel") -> str:
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            name = line[i + 1:].strip()
            return name or fallback
    return fallback


def _parse_m3u(text: str, country: str, source: str) -> list[dict]:
    out = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = _attrs(line)
            name = _extinf_name(line, attrs.get("tvg-name", "Channel"))
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


def _parse_xmltv_time(value: str) -> int:
    raw = str(value or "").strip()
    if not raw:
        return 0
    m = re.match(r"^(\d{14})(?:\s+([+-]\d{4}))?", raw)
    if not m:
        return 0
    base = m.group(1)
    offset = m.group(2) or "+0000"
    try:
        dt = datetime.strptime(base + " " + offset, "%Y%m%d%H%M%S %z")
        return int(dt.timestamp())
    except Exception:
        return 0


def _parse_epg_xml(text: str) -> tuple[dict, dict]:
    programmes = {}
    names = {}
    if not text or "<tv" not in text[:5000]:
        return programmes, names
    try:
        root = ET.fromstring(text)
    except Exception:
        return programmes, names

    for ch in root.findall("channel"):
        cid = str(ch.attrib.get("id") or "").strip()
        if not cid:
            continue
        display = ""
        node = ch.find("display-name")
        if node is not None and node.text:
            display = node.text.strip()
        if display:
            normalized = _normalize_name(display)
            names[normalized] = cid
            short = re.sub(r"^(?:am|ru)\s+", "", normalized).strip()
            if short and short != normalized:
                names.setdefault(short, cid)

    now = int(time.time())
    min_ts = now - 4 * 60 * 60
    max_ts = now + 36 * 60 * 60
    for p in root.findall("programme"):
        cid = str(p.attrib.get("channel") or "").strip()
        start = _parse_xmltv_time(p.attrib.get("start") or "")
        stop = _parse_xmltv_time(p.attrib.get("stop") or "")
        if not cid or not start or not stop or stop < min_ts or start > max_ts:
            continue
        title_node = p.find("title")
        desc_node = p.find("desc")
        title = (title_node.text or "").strip() if title_node is not None and title_node.text else ""
        desc = (desc_node.text or "").strip() if desc_node is not None and desc_node.text else ""
        programmes.setdefault(cid, []).append({
            "title": title or "Программа",
            "desc": desc[:300],
            "start": start,
            "stop": stop,
        })

    for rows in programmes.values():
        rows.sort(key=lambda x: x["start"])
    return programmes, names


async def refresh_epg(force: bool = False):
    now = int(time.time())
    if not force and _state["epg"] and now - int(_state["epg_last_refresh"] or 0) < EPG_REFRESH_SECONDS:
        return
    try:
        connector = aiohttp.TCPConnector(limit=8, ssl=False)
        async with aiohttp.ClientSession(connector=connector, headers={"User-Agent": "AbajTV/1.0"}) as session:
            texts = await asyncio.gather(*[_fetch_text(session, url) for _, url in EPG_URLS])
        all_programmes = {}
        all_names = {}
        for (_country, _url), text in zip(EPG_URLS, texts):
            programmes, names = _parse_epg_xml(text)
            for cid, rows in programmes.items():
                all_programmes.setdefault(cid, []).extend(rows)
            all_names.update(names)
        for rows in all_programmes.values():
            rows.sort(key=lambda x: x["start"])
        _state["epg"] = all_programmes
        _state["epg_names"] = all_names
        _state["epg_last_refresh"] = int(time.time())
        _state["epg_error"] = ""
    except Exception as exc:
        _state["epg_error"] = repr(exc)[:300]


def _epg_for_channel(item: dict) -> tuple[dict | None, dict | None]:
    cid = str(item.get("tvg_id") or "").strip()
    rows = _state["epg"].get(cid) if cid else None
    if not rows and cid:
        base_cid = cid.split("@", 1)[0].strip()
        rows = _state["epg"].get(base_cid) if base_cid else None
    if not rows:
        mapped = _state["epg_names"].get(_normalize_name(item.get("name") or ""))
        rows = _state["epg"].get(mapped) if mapped else None
    if not rows:
        return None, None
    now = int(time.time())
    current = None
    nxt = None
    for p in rows:
        if p["start"] <= now < p["stop"]:
            current = p
            continue
        if p["start"] > now:
            nxt = p
            break
    return current, nxt


def _fetch_text_sync(url: str) -> str:
    try:
        req = Request(url, headers={"User-Agent": "AbajTV/1.0"})
        with urlopen(req, timeout=45) as r:
            raw = r.read()
        return raw.decode("utf-8", "ignore")
    except Exception:
        return ""


async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status >= 400:
                return ""
            return await r.text(errors="ignore")
    except Exception:
        return await asyncio.to_thread(_fetch_text_sync, url)


async def _probe(session: aiohttp.ClientSession, item: dict, sem: asyncio.Semaphore) -> dict:
    started = None
    ok = False
    code = 0
    error = ""
    try:
        async with sem:
            started = time.perf_counter()
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
        "latency_ms": int((time.perf_counter() - (started or time.perf_counter())) * 1000),
        "error": error,
    })
    _record_health(row)
    h = _stream_health.get(str(row.get("url") or "")) or {}
    row["uptime_pct"] = float(h.get("uptime_pct") or 0.0)
    row["health_score"] = float(h.get("score") or _health_score(str(row.get("url") or "")))
    row["consecutive_failures"] = int(h.get("consecutive_failures") or 0)
    row["last_ok"] = int(h.get("last_ok") or 0)
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
                    -float(x.get("health_score") or _health_score(str(x.get("url") or ""))),
                    int(x.get("consecutive_failures") or 0),
                    int(x.get("latency_ms") or 999999),
                    0 if str(x.get("logo") or "").startswith("http") else 1,
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
                primary["backup_health"] = [
                    {
                        "url": x["url"],
                        "uptime_pct": float(x.get("uptime_pct") or 0.0),
                        "health_score": float(x.get("health_score") or 0.0),
                        "latency_ms": int(x.get("latency_ms") or 0),
                    }
                    for x in online_rows[1:] if x.get("url") != primary.get("url")
                ]
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
                "health_records": len(_stream_health),
                "stable_95": sum(1 for x in channels.values() if float(x.get("uptime_pct") or 0) >= 95.0),
            }
            try:
                _save_json(HEALTH_PATH, _stream_health)
                _save_json(SNAPSHOT_PATH, {"saved_at": int(time.time()), "state": public_state()})
            except Exception:
                pass
        except Exception as exc:
            _state["error"] = repr(exc)[:300]
        finally:
            _state["running"] = False


def public_state():
    rows = []
    for source in _state["channels"].values():
        row = dict(source)
        current, nxt = _epg_for_channel(row)
        row["epg_now"] = current if current is not None else row.get("epg_now")
        row["epg_next"] = nxt if nxt is not None else row.get("epg_next")
        rows.append(row)
    rows.sort(key=lambda x: (x["status"] != "ONLINE", x.get("country", ""), x.get("group", ""), x.get("name", "")))
    stats = dict(_state["stats"])
    stats["epg_channels"] = len(_state["epg"]) if _state["epg"] else int(stats.get("epg_channels") or 0)
    return {
        "ok": not bool(_state["error"]),
        "running": _state["running"],
        "last_refresh": _state["last_refresh"],
        "epg_last_refresh": _state["epg_last_refresh"],
        "stats": stats,
        "error": _state["error"],
        "epg_error": _state["epg_error"],
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
            "uptime_pct": x.get("uptime_pct", 0),
            "health_score": x.get("health_score", 0),
            "consecutive_failures": x.get("consecutive_failures", 0),
            "last_ok": x.get("last_ok", 0),
            "sources": x.get("sources", []),
            "last_failover": x.get("last_failover", 0),
            "failed_url": x.get("failed_url", ""),
            "backup_health": x.get("backup_health", []),
        }
        for x in rows
        if x.get("status") != "ONLINE" or int(x.get("backup_count") or 0) == 0
    ][:300]
    recent_failovers = sorted(
        [x for x in rows if int(x.get("last_failover") or 0) > 0],
        key=lambda x: int(x.get("last_failover") or 0),
        reverse=True,
    )[:50]
    return web.json_response({
        "ok": True,
        "stats": state.get("stats") or {},
        "last_refresh": state.get("last_refresh"),
        "running": state.get("running"),
        "problem_channels": problem,
        "recent_failovers": [
            {
                "id": x.get("id"),
                "name": x.get("name"),
                "last_failover": x.get("last_failover", 0),
                "failed_url": x.get("failed_url", ""),
                "backup_count": x.get("backup_count", 0),
            }
            for x in recent_failovers
        ],
    }, headers={"Cache-Control": "no-store"})


async def api_worker_command(request):
    supplied = (request.headers.get("X-IPTV-Worker-Token") or "").strip()
    expected = (os.getenv("IPTV_WORKER_TOKEN") or os.getenv("FACETALK_APK_DEPLOY_TOKEN") or os.getenv("INTERNAL_API_SECRET") or "").strip()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    requested = int(_worker_control.get("refresh_requested_at") or 0)
    last_snapshot = int(_worker_control.get("last_worker_snapshot") or 0)
    return web.json_response({
        "ok": True,
        "refresh": bool(requested and requested > last_snapshot),
        "refresh_requested_at": requested,
        "last_worker_snapshot": last_snapshot,
    }, headers={"Cache-Control": "no-store"})


async def api_worker_bootstrap(request):
    supplied = (request.headers.get("X-IPTV-Worker-Token") or "").strip()
    expected = (os.getenv("IPTV_WORKER_TOKEN") or os.getenv("FACETALK_APK_DEPLOY_TOKEN") or os.getenv("INTERNAL_API_SECRET") or "").strip()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    return web.json_response({"ok": True, "health": _stream_health}, headers={"Cache-Control": "no-store"})


async def api_worker_snapshot(request):
    supplied = (request.headers.get("X-IPTV-Worker-Token") or "").strip()
    expected = (os.getenv("IPTV_WORKER_TOKEN") or os.getenv("FACETALK_APK_DEPLOY_TOKEN") or os.getenv("INTERNAL_API_SECRET") or "").strip()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    body = await request.json()
    health = body.get("health") if isinstance(body, dict) else None
    if isinstance(health, dict):
        _stream_health.clear()
        for key, value in list(health.items())[:5000]:
            if isinstance(key, str) and isinstance(value, dict):
                _stream_health[key] = value
        try:
            _save_json(HEALTH_PATH, _stream_health)
        except Exception:
            pass
    state = body.get("state") if isinstance(body, dict) else None
    if not isinstance(state, dict) or not isinstance(state.get("channels"), list):
        return web.json_response({"ok": False, "error": "bad snapshot"}, status=400)
    channels = {}
    for row in state.get("channels") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        channels[str(row["id"])] = dict(row)
    if not channels:
        return web.json_response({"ok": False, "error": "empty snapshot"}, status=400)
    _state["channels"] = channels
    _state["last_refresh"] = int(state.get("last_refresh") or time.time())
    _state["stats"] = dict(state.get("stats") or {})
    _state["epg_last_refresh"] = int(state.get("epg_last_refresh") or 0)
    _state["epg_error"] = str(state.get("epg_error") or "")[:300]
    _state["error"] = str(state.get("error") or "")[:300]
    _worker_control["last_worker_snapshot"] = int(time.time())
    return web.json_response({"ok": True, "channels": len(channels), "last_refresh": _state["last_refresh"], "epg_last_refresh": _state["epg_last_refresh"]})


async def api_channels(request):
    if not _state["channels"]:
        await refresh_channels()
    return web.json_response(public_state(), headers={"Cache-Control": "no-store"})


async def api_refresh(request):
    worker_mode = str(os.getenv("IPTV_BACKGROUND_ENABLED", "1")).strip().lower() in {"0", "false", "no", "off"}
    if worker_mode:
        _worker_control["refresh_requested_at"] = int(time.time())
        return web.json_response({"ok": True, "queued": True, "worker": True})
    if _state["running"]:
        return web.json_response({"ok": True, "running": True})
    asyncio.create_task(refresh_channels(force=True))
    asyncio.create_task(refresh_epg(force=True))
    return web.json_response({"ok": True, "running": True})


async def api_play(request):
    cid = request.query.get("id", "")
    item = _state["channels"].get(cid)
    if not item or item.get("status") != "ONLINE":
        raise web.HTTPNotFound(text="Channel unavailable")

    urls = []
    original_primary = item.get("url") or ""
    for url in [original_primary, *(item.get("backups") or [])]:
        if url and url not in urls:
            urls.append(url)
    if request.query.get("failover") == "1" and len(urls) > 1:
        urls = urls[1:] + urls[:1]

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

                        if url != original_primary:
                            old_primary = original_primary
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
                                "X-IPTV-Source": "backup" if url != original_primary else "primary",
                                "X-IPTV-Backups": str(len(item.get("backups") or [])),
                            },
                        )

                    if ctype.startswith(("video/", "audio/")) or "octet-stream" in ctype:
                        if url != original_primary:
                            old_primary = original_primary
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
    if str(os.getenv("IPTV_BACKGROUND_ENABLED", "1")).strip().lower() in {"0", "false", "no", "off"}:
        app["iptv_task"] = None
        return
    async def loop():
        await asyncio.sleep(2)
        while True:
            await asyncio.gather(
                refresh_channels(force=True),
                refresh_epg(force=False),
            )
            await asyncio.sleep(REFRESH_SECONDS)
    app["iptv_task"] = asyncio.create_task(loop())


async def stop_background(app):
    task = app.get("iptv_task")
    if task:
        task.cancel()


def install(app: web.Application):
    app.router.add_get("/api/iptv/channels", api_channels)
    app.router.add_get("/api/iptv/worker-command", api_worker_command)
    app.router.add_get("/api/iptv/worker-bootstrap", api_worker_bootstrap)
    app.router.add_post("/api/iptv/worker-snapshot", api_worker_snapshot)
    app.router.add_get("/api/iptv/diagnostics", api_diagnostics)
    app.router.add_post("/api/iptv/refresh", api_refresh)
    app.router.add_get("/api/iptv/play", api_play)
    app.router.add_get("/api/iptv/proxy", api_proxy)
    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
