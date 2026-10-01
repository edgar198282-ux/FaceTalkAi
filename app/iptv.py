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

COUNTRY_CODES = {"AM", "RU", "GE", "UA", "BY", "KZ", "UZ", "MD"}
ADULT_KEYWORDS = re.compile(r'(^|[^a-z0-9])(18\+|xxx|adult|erotic|erotica|porn|porno|playboy|penthouse|hustler|dorcel|brazzers|redlight)([^a-z0-9]|$)', re.I)

def _is_adult_channel(row):
    raw = ' '.join(str(row.get(k) or '') for k in ('name','group','tvg_id')).lower()
    return bool(ADULT_KEYWORDS.search(raw))

SOURCE_URLS = [
    ("HQ", "https://dearbulut.github.io/iptv/playlists/best.m3u"),
    ("AM", "https://iptv-org.github.io/iptv/countries/am.m3u"),
    ("AM", "https://iptv-org.github.io/iptv/languages/hye.m3u"),
    ("AM", "https://dearbulut.github.io/iptv/playlists/country/am.m3u"),
    ("AM", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_armenia.m3u8"),
    ("RU", "https://iptv-org.github.io/iptv/countries/ru.m3u"),
    ("RU", "https://raw.githubusercontent.com/substanc1/iptv-russia/main/streams/ru.m3u"),
    ("RU", "https://ngrch.github.io/iptv/ru.m3u"),
    ("RU", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8"),
    ("GE", "https://iptv-org.github.io/iptv/countries/ge.m3u"),
    ("UA", "https://iptv-org.github.io/iptv/countries/ua.m3u"),
    ("BY", "https://iptv-org.github.io/iptv/countries/by.m3u"),
    ("KZ", "https://iptv-org.github.io/iptv/countries/kz.m3u"),
    ("UZ", "https://iptv-org.github.io/iptv/countries/uz.m3u"),
    ("MD", "https://iptv-org.github.io/iptv/countries/md.m3u"),
]
MAX_STREAMS = max(1500, int(os.getenv("IPTV_MAX_STREAMS", "3500")))
REFRESH_SECONDS = max(900, int(os.getenv("IPTV_REFRESH_SECONDS", "1800")))
PROBE_CONCURRENCY = 40
QUARANTINE_SECONDS = 60 * 60
DATA_ROOT = os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or os.path.join(os.getcwd(), "data")
HEALTH_PATH = os.path.join(DATA_ROOT, "iptv_health.json")
SNAPSHOT_PATH = os.path.join(DATA_ROOT, "iptv_snapshot.json")
HISTORY_PATH = os.path.join(DATA_ROOT, "iptv_scan_history.json")
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
    probe_latency = max(1, int(h.get("avg_latency_ms") or 2500))
    runtime_latency = max(1, int(h.get("runtime_startup_ms") or probe_latency))
    latency = int(probe_latency * 0.45 + runtime_latency * 0.55)
    consecutive = int(h.get("consecutive_failures") or 0)
    return round(uptime * 1000.0 - min(latency, 10000) / 22.0 - consecutive * 90.0, 3)

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
    # EPG.ONE currently provides a live multi-country XMLTV feed that includes
    # Armenia, Belarus, Georgia, Kazakhstan, Moldova, Russia, Ukraine and more.
    ("CIS", "https://epg.one/epg2.xml"),
]
IPTV_ORG_STREAMS_API = "https://iptv-org.github.io/api/streams.json"
IPTV_ORG_CHANNELS_API = "https://iptv-org.github.io/api/channels.json"
IPTV_ORG_LOGOS_API = "https://iptv-org.github.io/api/logos.json"
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
        "служеб", "тест", "резерв", "radio", "радио", "webcam",
        "promo", "preview", "placeholder", "mirror", "event feed"
    )
    if any(x in name for x in bad_name):
        return True
    if group in {"radio", "radios", "радио"}:
        return True
    # Do not pollute TV/4K rows with explicitly low-resolution mirrors.
    quality_text = " ".join((name, group))
    if re.search(r"(^|[^0-9])(240p?|360p?|480p?|576p?)([^0-9]|$)", quality_text, re.I):
        return True
    if re.search(r"(^|[^a-z])(low[ ._-]?quality|low[ ._-]?res)([^a-z]|$)", quality_text, re.I):
        return True
    if not url.startswith(("http://", "https://")):
        return True
    return False


def _is_quarantined(url: str, now: int | None = None) -> bool:
    h = _stream_health.get(str(url or "")) or {}
    samples = int(h.get("successes") or 0) + int(h.get("failures") or 0)
    if samples < 4 or int(h.get("consecutive_failures") or 0) < 3:
        return False
    if float(h.get("uptime_pct") or 0.0) >= 25.0:
        return False
    last_fail = int(h.get("last_fail") or 0)
    if not last_fail:
        return False
    return int(now or time.time()) - last_fail < QUARANTINE_SECONDS


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


def _parse_hq_m3u(text: str, source: str) -> list[dict]:
    out = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = _attrs(line)
            country = str(attrs.get("tvg-country") or "").strip().upper()
            if country not in COUNTRY_CODES:
                pending = None
                continue
            score = int(attrs.get("nexus-score") or 0)
            if score < 90:
                pending = None
                continue
            name = _extinf_name(line, attrs.get("tvg-name", "Channel"))
            raw_quality = " ".join([name or "", attrs.get("tvg-name", ""), attrs.get("group-title", "")])
            is_4k = bool(re.search(r"(^|[^a-z0-9])(4k|4к|uhd|2160p?|3840x2160)([^a-z0-9]|$)", raw_quality, re.I))
            is_fhd = bool(re.search(r"(^|[^a-z0-9])(fhd|full[ ._-]?hd|1080p?|1920x1080)([^a-z0-9]|$)", raw_quality, re.I))
            if not (is_4k or is_fhd):
                pending = None
                continue
            pending = {
                "name": name or "Channel",
                "group": attrs.get("group-title", "") or "Other",
                "tvg_id": attrs.get("tvg-id", ""),
                "logo": attrs.get("tvg-logo", ""),
                "country": country,
                "source": source,
                "quality": "4K" if is_4k else "FHD",
                "height": 2160 if is_4k else 1080,
            }
        elif not line.startswith("#") and pending and line.startswith(("http://", "https://")):
            row = dict(pending)
            row["url"] = line
            key_src = _channel_key(row)
            if key_src:
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
        # XMLTV feeds often expose several display-name variants for the same
        # channel (local language, latin spelling, short name). Index all of
        # them instead of only the first one so playlist names match far more
        # reliably without fuzzy guesses.
        aliases = []
        for node in ch.findall("display-name"):
            if node is not None and node.text:
                value = node.text.strip()
                if value and value not in aliases:
                    aliases.append(value)
        # The XMLTV channel id itself is also useful as a conservative alias.
        aliases.append(cid)
        base_cid = cid.split("@", 1)[0].strip()
        if base_cid and base_cid != cid:
            aliases.append(base_cid)
        for display in aliases:
            normalized = _normalize_name(display)
            if not normalized:
                continue
            names.setdefault(normalized, cid)
            short = re.sub(r"^(?:am|ru|ua|by|kz|uz|md|ge)\s+", "", normalized).strip()
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
        parsed_feeds = await asyncio.gather(
            *[asyncio.to_thread(_parse_epg_xml, text) for text in texts]
        )
        for programmes, names in parsed_feeds:
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
        aliases = [item.get("name") or ""] + list(item.get("epg_aliases") or [])
        for alias in aliases:
            normalized = _normalize_name(alias)
            if not normalized:
                continue
            mapped = _state["epg_names"].get(normalized)
            if not mapped:
                # Common provider prefixes/suffixes differ between playlists and XMLTV.
                short = re.sub(r"^(?:am|ru|ua|by|kz|uz|md|ge)\s+", "", normalized).strip()
                mapped = _state["epg_names"].get(short) if short and short != normalized else None
            if mapped:
                rows = _state["epg"].get(mapped)
                if rows:
                    break
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


async def _discover_iptv_org_api(session: aiohttp.ClientSession) -> list[dict]:
    """Discover current public streams from iptv-org and normalize them into our candidate format."""
    try:
        async def get_json(url):
            try:
                text = await _fetch_text(session, url)
                data = json.loads(text) if text else []
                return data if isinstance(data, list) else []
            except Exception:
                return []
        streams, channels_meta, logos = await asyncio.gather(
            get_json(IPTV_ORG_STREAMS_API), get_json(IPTV_ORG_CHANNELS_API), get_json(IPTV_ORG_LOGOS_API)
        )
        meta = {str(x.get('id') or ''): x for x in channels_meta if isinstance(x, dict) and x.get('id')}
        logo_map = {}
        for x in logos:
            if not isinstance(x, dict) or not x.get('channel') or not x.get('url'):
                continue
            cid = str(x.get('channel'))
            if cid not in logo_map or bool(x.get('in_use')):
                logo_map[cid] = str(x.get('url'))
        out = []
        for s in streams:
            if not isinstance(s, dict):
                continue
            channel_id = str(s.get('channel') or '').strip()
            url = str(s.get('url') or '').strip()
            if not channel_id or not url:
                continue
            m = meta.get(channel_id) or {}
            country = str(m.get('country') or '').upper()
            if country not in COUNTRY_CODES:
                continue
            labels = {str(x).lower() for x in (s.get('labels') or [])}
            if 'not 24/7' in labels:
                continue
            q = str(s.get('quality') or '').lower()
            height = 0
            qm = re.search(r'(\d{3,4})p', q)
            if qm:
                height = int(qm.group(1))
            quality = '4K' if height >= 2000 else ('FHD' if height >= 1000 else ('HD' if height >= 700 else ''))
            categories = [str(x) for x in (m.get('categories') or []) if x]
            adult = bool(m.get('is_nsfw'))
            group = 'Adult' if adult else (categories[0].title() if categories else 'General')
            aliases = []
            for alias in [m.get('name'), *(m.get('alt_names') or []), m.get('network')]:
                alias = str(alias or '').strip()
                if alias and alias not in aliases:
                    aliases.append(alias)
            item = {
                'name': str(m.get('name') or s.get('title') or channel_id),
                'epg_aliases': aliases[:12],
                'group': group,
                'tvg_id': channel_id,
                'logo': logo_map.get(channel_id, ''),
                'country': country,
                'source': 'iptv-org-api',
                'url': url,
                'adult': adult,
                'quality': quality,
                'height': height,
            }
            key_src = _channel_key(item)
            if not key_src or _looks_junk(item):
                continue
            item['id'] = hashlib.sha1(key_src.encode('utf-8')).hexdigest()[:16]
            out.append(item)
        return out
    except Exception:
        return []


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
    row["runtime_startup_ms"] = int(h.get("runtime_startup_ms") or 0)
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
                fetched, discovered_api = await asyncio.gather(
                    asyncio.gather(*[_fetch_text(session, url) for _, url in SOURCE_URLS]),
                    _discover_iptv_org_api(session),
                )
                candidates = []
                for (country, url), text in zip(SOURCE_URLS, fetched):
                    if "#EXTM3U" not in text[:4096]:
                        continue
                    if country == "HQ":
                        candidates.extend(_parse_hq_m3u(text, url))
                    else:
                        candidates.extend(_parse_m3u(text, country, url))
                candidates.extend(discovered_api)
                # Enrich legacy M3U rows with logos discovered from the fresh API.
                # Prefer exact tvg-id, then normalized channel name within the same country.
                logo_by_id = {}
                logo_by_name = {}
                for x in discovered_api:
                    logo = str(x.get('logo') or '').strip()
                    if not logo:
                        continue
                    tvg_id = str(x.get('tvg_id') or '').strip().lower()
                    if tvg_id and tvg_id not in logo_by_id:
                        logo_by_id[tvg_id] = logo
                    aliases = [x.get('name') or ''] + list(x.get('epg_aliases') or [])
                    for alias in aliases:
                        normalized = _normalize_name(alias)
                        nkey = (str(x.get('country') or '').upper(), normalized)
                        if normalized and nkey not in logo_by_name:
                            logo_by_name[nkey] = logo
                enriched_logos = 0
                country_order = {code: i for i, code in enumerate(("AM","RU","GE","UA","BY","KZ","UZ","MD"))}
                for item in candidates:
                    item['adult'] = bool(item.get('adult')) or _is_adult_channel(item)
                    if not str(item.get('logo') or '').strip():
                        tvg_id = str(item.get('tvg_id') or '').strip().lower()
                        logo = logo_by_id.get(tvg_id) if tvg_id else None
                        if not logo:
                            logo = logo_by_name.get((str(item.get('country') or '').upper(), _normalize_name(item.get('name') or '')))
                        if logo:
                            item['logo'] = logo
                            enriched_logos += 1
                candidates.sort(key=lambda x: (
                    country_order.get(str(x.get("country") or "").upper(), 99),
                    0 if str(x.get("quality") or "").upper() in {"4K", "FHD"} else 1,
                ))
                # First fill the probe budget with one stream per channel so large
                # playlists cannot crowd out many distinct channels. Then use the
                # remaining budget for backup streams.
                seen_urls = set()
                seen_channels = set()
                unique = []
                backups = []
                for item in candidates:
                    url = item.get("url")
                    cid = item.get("id")
                    if not url or not cid or url in seen_urls:
                        continue
                    # Repeatedly dead streams are temporarily quarantined. They are
                    # retried automatically after the quarantine window expires.
                    if _is_quarantined(url, now):
                        continue
                    seen_urls.add(url)
                    if cid not in seen_channels:
                        seen_channels.add(cid)
                        unique.append(item)
                    else:
                        backups.append(item)
                    if len(unique) >= MAX_STREAMS:
                        break
                if len(unique) < MAX_STREAMS:
                    unique.extend(backups[:MAX_STREAMS-len(unique)])
                sem = asyncio.Semaphore(PROBE_CONCURRENCY)
                checked = await asyncio.gather(*[_probe(session, item, sem) for item in unique])
            grouped = {}
            for item in checked:
                grouped.setdefault(item["id"], []).append(item)

            channels = {}
            for cid, rows in grouped.items():
                rows.sort(key=lambda x: (
                    x.get("status") != "ONLINE",
                    0 if str(x.get("quality") or "").upper() == "4K" else (1 if str(x.get("quality") or "").upper() == "FHD" else 2),
                    -float(x.get("health_score") or _health_score(str(x.get("url") or ""))),
                    int(x.get("consecutive_failures") or 0),
                    int(x.get("runtime_startup_ms") or 999999),
                    int(x.get("latency_ms") or 999999),
                    0 if str(x.get("logo") or "").startswith("http") else 1,
                ))
                primary = dict(rows[0])
                # If the fastest/best stream has no logo but another stream for
                # the same channel does, keep the best stream and inherit the logo.
                if not str(primary.get("logo") or "").strip():
                    inherited_logo = next((str(x.get("logo") or "").strip() for x in rows if str(x.get("logo") or "").strip()), "")
                    if inherited_logo:
                        primary["logo"] = inherited_logo
                        enriched_logos += 1

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
                health = _stream_health.get(str(primary.get("url") or "")) or {}
                samples = int(health.get("successes") or 0) + int(health.get("failures") or 0)
                primary["health_samples"] = samples
                primary["unreliable"] = bool(samples >= 6 and float(primary.get("uptime_pct") or 0.0) < 40.0)
                primary["candidate_count"] = len(rows)
                primary["duplicate_count"] = max(0, len(rows) - 1)
                primary["sources"] = sorted({str(x.get("source") or "") for x in rows if x.get("source")})
                primary["normalized_name"] = _normalize_name(primary.get("name") or "")
                primary["last_checked"] = int(time.time())
                channels[cid] = primary

            previous_channels = dict(_state.get("channels") or {})
            previous_ids = set(previous_channels)
            current_ids = set(channels)
            online = sum(1 for x in channels.values() if x.get("status") == "ONLINE")
            newly_found = current_ids - previous_ids if previous_ids else set()
            disappeared = previous_ids - current_ids if previous_ids else set()
            recovered = 0
            newly_offline = 0
            if previous_ids:
                for cid in current_ids & previous_ids:
                    before = str((previous_channels.get(cid) or {}).get("status") or "")
                    after = str((channels.get(cid) or {}).get("status") or "")
                    if before != "ONLINE" and after == "ONLINE":
                        recovered += 1
                    elif before == "ONLINE" and after != "ONLINE":
                        newly_offline += 1
            quarantined_streams = sum(1 for url in _stream_health if _is_quarantined(url, now))
            _state["channels"] = channels
            _state["last_refresh"] = int(time.time())
            _state["stats"] = {
                "total": len(channels),
                "online": online,
                "offline": len(channels) - online,
                "source_count": len(SOURCE_URLS),
                "candidate_streams": len(checked),
                "max_streams": MAX_STREAMS,
                "duplicates_removed": max(0, len(checked) - len(channels)),
                "with_backups": sum(1 for x in channels.values() if int(x.get("backup_count") or 0) > 0),
                "health_records": len(_stream_health),
                "stable_95": sum(1 for x in channels.values() if float(x.get("uptime_pct") or 0) >= 95.0),
                "new_channels": len(newly_found),
                "disappeared_channels": len(disappeared),
                "recovered_channels": recovered,
                "newly_offline": newly_offline,
                "quarantined_streams": quarantined_streams,
                "adult_channels": sum(1 for x in channels.values() if bool(x.get("adult"))),
                "with_logo": sum(1 for x in channels.values() if bool(x.get("logo"))),
                "with_epg": sum(1 for x in channels.values() if bool(x.get("epg_now"))),
                "scan_interval_seconds": 1800,
                "discovered_api_streams": len(discovered_api),
                "logos_enriched": enriched_logos,
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


def public_state(compact: bool = False):
    rows = []
    compact_keys = {
        "id", "name", "group", "country", "logo", "status", "tvg_id",
        "quality", "height",
        "latency_ms", "backup_count", "epg_now", "epg_next",
        "unreliable", "adult"
    }
    for source in _state["channels"].values():
        row = dict(source)
        current, nxt = _epg_for_channel(row)
        row["epg_now"] = current if current is not None else row.get("epg_now")
        row["epg_next"] = nxt if nxt is not None else row.get("epg_next")
        if compact:
            row = {k: row.get(k) for k in compact_keys if k in row}
            for epg_key in ("epg_now", "epg_next"):
                epg = row.get(epg_key)
                if isinstance(epg, dict):
                    row[epg_key] = {
                        "title": epg.get("title"),
                        "start": epg.get("start"),
                        "stop": epg.get("stop"),
                    }
        rows.append(row)
    rows.sort(key=lambda x: (x["status"] != "ONLINE", x.get("country", ""), x.get("group", ""), x.get("name", "")))
    stats = dict(_state["stats"])
    stats["epg_channels"] = len(_state["epg"]) if _state["epg"] else int(stats.get("epg_channels") or 0)
    stats["with_epg"] = sum(1 for x in rows if bool(x.get("epg_now")))
    stats["with_logo"] = sum(1 for x in rows if bool(x.get("logo")))
    coverage_by_country = {}
    for x in rows:
        code = str(x.get("country") or "??").upper()
        c = coverage_by_country.setdefault(code, {"total":0,"online":0,"epg":0,"logo":0,"backup":0})
        c["total"] += 1
        if x.get("status") == "ONLINE": c["online"] += 1
        if x.get("epg_now"): c["epg"] += 1
        if x.get("logo"): c["logo"] += 1
        if int(x.get("backup_count") or 0) > 0: c["backup"] += 1
    stats["coverage_by_country"] = coverage_by_country
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
    history = _load_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    return web.json_response({
        "ok": True,
        "stats": state.get("stats") or {},
        "scan_history": history[-48:],
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
                "failover_count": x.get("failover_count", 0),
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
    try:
        history = _load_json(HISTORY_PATH, [])
        if not isinstance(history, list):
            history = []
        st = _state["stats"]
        entry = {
            "ts": int(time.time()),
            "total": int(st.get("total") or len(channels)),
            "online": int(st.get("online") or 0),
            "offline": int(st.get("offline") or 0),
            "with_backups": int(st.get("with_backups") or 0),
            "with_logo": int(st.get("with_logo") or 0),
            "with_epg": int(st.get("with_epg") or 0),
            "quarantined_streams": int(st.get("quarantined_streams") or 0),
            "discovered_api_streams": int(st.get("discovered_api_streams") or 0),
            "candidate_streams": int(st.get("candidate_streams") or 0),
        }
        # Avoid duplicate entries when the same worker snapshot is retried.
        if not history or int(history[-1].get("ts") or 0) < entry["ts"] - 10:
            history.append(entry)
            history = history[-96:]
            _save_json(HISTORY_PATH, history)
    except Exception:
        pass
    incoming_epg_refresh = int(state.get("epg_last_refresh") or 0)
    if incoming_epg_refresh > 0:
        _state["epg_last_refresh"] = incoming_epg_refresh
    incoming_epg_error = str(state.get("epg_error") or "")[:300]
    if incoming_epg_error:
        _state["epg_error"] = incoming_epg_error
    _state["error"] = str(state.get("error") or "")[:300]
    _worker_control["last_worker_snapshot"] = int(time.time())
    return web.json_response({"ok": True, "channels": len(channels), "last_refresh": _state["last_refresh"], "epg_last_refresh": _state["epg_last_refresh"]})


async def api_channels(request):
    if not _state["channels"]:
        await refresh_channels()
    compact = request.query.get("compact") == "1"
    return web.json_response(public_state(compact=compact), headers={"Cache-Control": "no-store"})


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

    prefer_backup = request.query.get("failover") == "1" and len(urls) > 1
    primary_candidates = urls[1:] if prefer_backup else urls[:3]
    fallback_candidates = [original_primary] if prefer_backup and original_primary else []

    timeout = aiohttp.ClientTimeout(total=6, connect=2.5, sock_read=3.5)

    async def race_candidates(session, candidates):
        async def probe_candidate(url):
            started = time.perf_counter()
            response = None
            try:
                response = await session.get(url, timeout=timeout, allow_redirects=True)
                ctype = (response.headers.get("content-type") or "").lower()
                final_url = str(response.url)
                if response.status >= 400:
                    return {"ok": False, "error": f"HTTP {response.status}", "url": url}

                is_hls = "mpegurl" in ctype or urlparse(final_url).path.lower().endswith(".m3u8")
                if is_hls:
                    body = await response.read()
                    if b"#EXTM3U" not in body[:4096] and "mpegurl" not in ctype:
                        return {"ok": False, "error": "invalid HLS manifest", "url": url}
                    return {
                        "ok": True,
                        "kind": "hls",
                        "url": url,
                        "final_url": final_url,
                        "body": body,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }

                if ctype.startswith(("video/", "audio/")) or "octet-stream" in ctype:
                    return {
                        "ok": True,
                        "kind": "redirect",
                        "url": url,
                        "final_url": final_url,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }
                return {"ok": False, "error": f"unsupported content-type {ctype}", "url": url}
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:160], "url": url}
            finally:
                if response is not None:
                    response.release()

        tasks = [asyncio.create_task(probe_candidate(url)) for url in candidates if url]
        if not tasks:
            return None, "no candidates"
        last_error = ""
        winner = None
        try:
            for future in asyncio.as_completed(tasks):
                result = await future
                if result and result.get("ok"):
                    winner = result
                    break
                if result:
                    last_error = str(result.get("error") or last_error)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return winner, last_error

    headers = {"User-Agent": "IPTV-Player/1.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        winner, last_error = await race_candidates(session, primary_candidates)
        if winner is None and fallback_candidates:
            winner, fallback_error = await race_candidates(session, fallback_candidates)
            if fallback_error:
                last_error = fallback_error

    if winner is None:
        raise web.HTTPBadGateway(text="All channel streams failed: " + (last_error or "no response"))

    selected_url = winner["url"]
    latency_ms = int(winner.get("latency_ms") or 0)
    health = dict(_stream_health.get(selected_url) or {})
    old_runtime = int(health.get("runtime_startup_ms") or latency_ms or 0)
    if latency_ms:
        health["runtime_startup_ms"] = latency_ms if not old_runtime else int(old_runtime * 0.7 + latency_ms * 0.3)
    health["last_runtime_ok"] = int(time.time())
    _stream_health[selected_url] = health

    if selected_url != original_primary:
        old_primary = original_primary
        item["url"] = selected_url
        item["backups"] = [x for x in urls if x != selected_url]
        item["backup_count"] = len(item["backups"])
        item["last_failover"] = int(time.time())
        item["failover_count"] = int(item.get("failover_count") or 0) + 1
        item["failed_url"] = old_primary or ""

    if winner["kind"] == "redirect" or request.query.get("proxy") != "1":
        raise web.HTTPTemporaryRedirect(winner["final_url"])

    text_body = winner["body"].decode("utf-8", "ignore")
    return web.Response(
        text=_rewrite_hls(text_body, winner["final_url"]),
        content_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-store",
            "X-IPTV-Source": "backup" if selected_url != original_primary else "primary",
            "X-IPTV-Backups": str(len(item.get("backups") or [])),
            "X-IPTV-Startup-Ms": str(latency_ms),
        },
    )

async def api_proxy(request):
    url = request.query.get("u", "")
    sig = request.query.get("s", "")
    if not url.startswith(("http://", "https://")) or not hmac.compare_digest(sig, _token(url)):
        raise web.HTTPForbidden(text="Invalid stream token")
    timeout = aiohttp.ClientTimeout(total=None, connect=3, sock_read=10)
    session = aiohttp.ClientSession(headers={"User-Agent": "IPTV-Player/1.0"})
    try:
        r = await session.get(url, timeout=timeout, allow_redirects=True)
        ctype = (r.headers.get("content-type") or "").lower()
        final_url = str(r.url)
        status = r.status
        is_hls = "mpegurl" in ctype or urlparse(final_url).path.lower().endswith(".m3u8")
        if is_hls:
            body = await r.read()
            await r.release()
            await session.close()
            return web.Response(
                text=_rewrite_hls(body.decode("utf-8", "ignore"), final_url),
                content_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-store"},
            )

        content_type = ctype.split(";")[0] if ctype else "application/octet-stream"
        resp = web.StreamResponse(
            status=status,
            headers={
                "Content-Type": content_type,
                "Cache-Control": "private, max-age=30",
            },
        )
        if r.content_length is not None:
            resp.content_length = r.content_length
        await resp.prepare(request)
        try:
            async for chunk in r.content.iter_chunked(64 * 1024):
                await resp.write(chunk)
            await resp.write_eof()
        finally:
            r.release()
            await session.close()
        return resp
    except Exception:
        await session.close()
        raise


async def start_background(app):
    worker_mode = str(os.getenv("IPTV_BACKGROUND_ENABLED", "1")).strip().lower() in {"0", "false", "no", "off"}

    # EPG must live in the main web process because public channel responses are
    # enriched there. Keep this lightweight task active even when channel scans
    # are delegated to the separate worker.
    async def epg_loop():
        await asyncio.sleep(2)
        while True:
            await refresh_epg(force=False)
            await asyncio.sleep(EPG_REFRESH_SECONDS)
    app["iptv_epg_task"] = asyncio.create_task(epg_loop())

    if worker_mode:
        app["iptv_task"] = None
        return

    async def loop():
        await asyncio.sleep(2)
        while True:
            await refresh_channels(force=True)
            await asyncio.sleep(REFRESH_SECONDS)
    app["iptv_task"] = asyncio.create_task(loop())


async def stop_background(app):
    for key in ("iptv_task", "iptv_epg_task"):
        task = app.get(key)
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
