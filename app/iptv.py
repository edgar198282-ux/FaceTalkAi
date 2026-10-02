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
AD_HISTORY_PATH = os.path.join(DATA_ROOT, "iptv_ad_history.json")
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

def _is_wink_placeholder_stream(item: dict) -> bool:
    """Reject known Wink/Nginex territorial placeholder streams before probing."""
    url = str(item.get("url") or "").strip()
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return bool(host == "ngenix.net" or host.endswith(".ngenix.net"))


def _hide_unusable_catalog_channel(item: dict) -> bool:
    """Hide channels that are known duplicates/restricted placeholders, not useful live TV."""
    name = str(item.get("name") or "").strip()
    source = str(item.get("source") or "").lower()
    group = str(item.get("group") or "").lower()

    # Explicit upstream warnings: these routinely resolve at HTTP level but do
    # not provide a usable continuous live channel.
    if re.search(r"\[(?:[^\]]*geo[- ]?blocked|[^\]]*not\s*24/?7)[^\]]*\]", name, flags=re.I):
        return True

    # Regional time-shift copies from the ngrch Russian playlist are mostly
    # Wink/Nginex rebroadcasts. Outside their territory many display a Wink
    # restriction slate while still looking ONLINE to an HTTP probe.
    if "ngrch.github.io/iptv/ru.m3u" in source and "регион" in group:
        if re.search(r"\(\s*[+-]\s*\d{1,2}\s*\)\s*$", name):
            return True

    return False


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
    # Primary CIS guide.
    ("CIS", "https://epg.one/epg2.xml"),
    # Extra current XMLTV sources. RU adds much broader Russian coverage;
    # Lite contributes additional popular channels from multiple countries.
    ("EPGPW_RU", "https://epg.pw/xmltv/epg_RU.xml"),
    ("EPGPW_LITE", "https://epg.pw/xmltv/epg_lite.xml"),
]
IPTV_ORG_STREAMS_API = "https://iptv-org.github.io/api/streams.json"
IPTV_ORG_CHANNELS_API = "https://iptv-org.github.io/api/channels.json"
IPTV_ORG_LOGOS_API = "https://iptv-org.github.io/api/logos.json"
RU_LOGO_CATALOG_URL = "https://raw.githubusercontent.com/naggdd/iptv/main/ru.m3u"
RU_LOGO_ID_CATALOG_URL = "https://raw.githubusercontent.com/swoldier-rus/IP_TV/main/sw.m3u"
FREE_TV_LOGO_CATALOG_URLS = {
    "AM": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_armenia.m3u8",
    "RU": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    "GE": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_georgia.m3u8",
    "UA": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_ukraine.m3u8",
    "BY": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_belarus.m3u8",
    "KZ": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_kazakhstan.m3u8",
    "MD": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_moldova.m3u8",
}
TV_LOGO_MANIFEST_URL = "https://raw.githubusercontent.com/dj1p/tvlogos/main/logos-manifest.json"
TV_LOGO_MANIFEST_BASE = "https://raw.githubusercontent.com/dj1p/tvlogos/main"
EPG_REFRESH_SECONDS = 3 * 60 * 60

_state = {
    "channels": {},
    "last_refresh": 0,
    "running": False,
    "stats": {"total": 0, "online": 0, "offline": 0},
    "error": "",
    "epg": {},
    "epg_names": {},
    "epg_logos": {},
    "epg_logo_names": {},
    "epg_last_refresh": 0,
    "epg_error": "",
}
_lock = asyncio.Lock()
_proxy_secret = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("FACETALK_BOT_TOKEN") or "iptv-player").encode()
_worker_control = {"refresh_requested_at": 0, "last_worker_snapshot": 0}

_ad_probe_cache = {}
_ad_last_state = {}
_ad_scan_stats = {"probes": 0, "errors": 0, "last_probe": 0, "last_channel_id": "", "tag_counts": {}}
_burned_ad_stats = {
    "samples": 0,
    "channels": {},
    "high_score_count": 0,
    "last_score": 0,
    "last_channel_id": "",
    "last_seen": 0,
    "last_free_play": 0,
    "last_free_play_channel_id": "",
    "server_probes": 0,
    "server_probe_errors": 0,
    "server_last_probe": 0,
    "server_last_score": 0,
}
_burned_ad_last_report = {}
_ottclub_quick_inflight = set()
_ottclub_ad_state = {}
_cinerama_placeholder_state = {}
_cinerama_stats = {
    "probes": 0,
    "detections": 0,
    "active_channels": 0,
    "last_channel_id": "",
    "last_hits": 0,
    "last_probe": 0,
}
_ottclub_stats = {
    "probes": 0,
    "errors": 0,
    "detections": 0,
    "last_probe": 0,
    "last_channel_id": "",
    "last_hits": 0,
    "last_text": "",
}
_compact_response_cache = {"key": None, "body": b"", "expires_at": 0.0}

def _record_ad_transition(item: dict, active: bool, marker: str):
    cid = str(item.get("id") or "")
    if not cid:
        return
    previous = bool(_ad_last_state.get(cid, False))
    if previous == bool(active):
        return
    _ad_last_state[cid] = bool(active)
    try:
        history = _load_json(AD_HISTORY_PATH, [])
        if not isinstance(history, list):
            history = []
        history.append({
            "ts": int(time.time()),
            "channel_id": cid,
            "name": str(item.get("name") or "")[:160],
            "country": str(item.get("country") or "")[:8],
            "active": bool(active),
            "marker": str(marker or "")[:40],
        })
        _save_json(AD_HISTORY_PATH, history[-500:])
    except Exception:
        pass

def _detect_hls_ad_break(text: str) -> tuple[bool, str]:
    if not text or "#EXTM3U" not in text[:4096]:
        return False, ""
    active = False
    marker = ""
    for raw in text.splitlines():
        line = raw.strip()
        upper = line.upper()
        if not upper:
            continue
        if upper.startswith("#EXT-X-CUE-OUT") or "SCTE35-OUT" in upper:
            active = True
            marker = "cue-out"
            continue
        if upper.startswith("#EXT-X-CUE-IN") or "SCTE35-IN" in upper:
            active = False
            marker = "cue-in"
            continue
        if upper.startswith("#EXT-X-DATERANGE"):
            attrs = {k.upper(): v for k, v in re.findall(r'([A-Z0-9-]+)="?([^",]+)"?', upper)}
            klass = str(attrs.get("CLASS") or "")
            has_scte_out = "SCTE35-OUT" in upper or "SCTE35-CMD" in upper
            has_scte_in = "SCTE35-IN" in upper
            ad_class = any(token in klass for token in ("AD", "SCTE", "INTERSTITIAL", "CUE"))
            ended = "END-DATE=" in upper or "END-ON-NEXT=YES" in upper
            if has_scte_in or (ad_class and ended and not has_scte_out):
                active = False
                marker = "daterange-in"
            elif has_scte_out or ad_class:
                active = True
                marker = "daterange-out"
    return active, marker

async def _free_channel_ad_state(item: dict) -> dict:
    cid = str(item.get("id") or "")
    now = time.time()
    _ad_scan_stats["probes"] = int(_ad_scan_stats.get("probes") or 0) + 1
    _ad_scan_stats["last_probe"] = int(now)
    _ad_scan_stats["last_channel_id"] = cid
    cached = _ad_probe_cache.get(cid) or {}
    if now - float(cached.get("checked_at") or 0) < 2.5:
        return cached
    result = {"active": False, "marker": "", "checked_at": now}
    url = str(item.get("url") or "")
    if not url.startswith(("http://", "https://")):
        _ad_probe_cache[cid] = result
        return result
    try:
        timeout = aiohttp.ClientTimeout(total=5, connect=2.5, sock_read=3)
        headers = {"User-Agent": "AbajTV/1.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async def fetch_manifest(target: str) -> str:
                try:
                    async with session.get(target, allow_redirects=True) as response:
                        if response.status >= 400:
                            return ""
                        return await response.text(errors="ignore")
                except Exception:
                    return ""
            text = await fetch_manifest(url)
            if "#EXTM3U" not in text[:4096]:
                _ad_probe_cache[cid] = result
                return result
            # If this is a master playlist, inspect the first media variant.
            if "#EXT-X-STREAM-INF" in text:
                media_url = ""
                expect_uri = False
                for raw in text.splitlines():
                    line = raw.strip()
                    if line.startswith("#EXT-X-STREAM-INF"):
                        expect_uri = True
                        continue
                    if expect_uri and line and not line.startswith("#"):
                        media_url = urljoin(url, line)
                        break
                if media_url:
                    text = await fetch_manifest(media_url)
            upper_manifest = text.upper()
            observed = []
            for tag in ("#EXT-X-CUE-OUT", "#EXT-X-CUE-IN", "#EXT-X-DATERANGE", "SCTE35-OUT", "SCTE35-IN", "SCTE35-CMD", "#EXT-X-INTERSTITIAL"):
                if tag in upper_manifest:
                    observed.append(tag)
                    counts = _ad_scan_stats.setdefault("tag_counts", {})
                    counts[tag] = int(counts.get(tag) or 0) + 1
            # Keep only aggregate names of uncommon HLS tags for diagnostics.
            # Never store segment URLs or manifest bodies.
            uncommon = _ad_scan_stats.setdefault("other_hls_tags", {})
            common_tags = {
                "#EXTM3U", "#EXTINF", "#EXT-X-VERSION", "#EXT-X-TARGETDURATION",
                "#EXT-X-MEDIA-SEQUENCE", "#EXT-X-KEY", "#EXT-X-MAP",
                "#EXT-X-PROGRAM-DATE-TIME", "#EXT-X-DISCONTINUITY",
                "#EXT-X-ENDLIST", "#EXT-X-INDEPENDENT-SEGMENTS",
                "#EXT-X-STREAM-INF", "#EXT-X-MEDIA", "#EXT-X-BYTERANGE",
            }
            for raw_line in text.splitlines():
                tag_line = raw_line.strip().upper()
                if not tag_line.startswith("#"):
                    continue
                tag_name = tag_line.split(":", 1)[0]
                if tag_name.startswith("#EXT") and tag_name not in common_tags and tag_name not in {
                    "#EXT-X-CUE-OUT", "#EXT-X-CUE-IN", "#EXT-X-DATERANGE", "#EXT-X-INTERSTITIAL"
                }:
                    uncommon[tag_name] = int(uncommon.get(tag_name) or 0) + 1
            if len(uncommon) > 30:
                top = sorted(uncommon.items(), key=lambda kv: kv[1], reverse=True)[:30]
                _ad_scan_stats["other_hls_tags"] = dict(top)
            result["observed_tags"] = observed
            result["marker_capable"] = bool(observed)
            active, marker = _detect_hls_ad_break(text)
            result.update({"active": bool(active), "marker": marker})
            _record_ad_transition(item, bool(active), marker)
    except Exception as exc:
        _ad_scan_stats["errors"] = int(_ad_scan_stats.get("errors") or 0) + 1
        result["error"] = str(exc)[:120]
    _ad_probe_cache[cid] = result
    return result


async def _ocr_ottclub_frame(frame: bytes, width: int, height: int) -> str:
    if not frame:
        return ""
    pgm = f"P5\n{width} {height}\n255\n".encode("ascii") + frame
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "tesseract", "stdin", "stdout", "--psm", "11", "-l", "eng",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(input=pgm), timeout=4)
        return stdout.decode("utf-8", "ignore")[:1200]
    except Exception:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        return ""


def _cinerama_text_hit(text: str) -> bool:
    raw = str(text or "").upper()
    compact = re.sub(r"[^A-Z0-9]+", "", raw)
    normalized = compact.replace("1", "I").replace("0", "O")
    return (
        "CINERAMA" in normalized
        or "CINERAMAUZ" in normalized
        or bool(re.search(r"C[I1]NE\s*RAMA", raw))
    )


def _ottclub_text_hit(text: str) -> bool:
    raw = str(text or "").upper()
    compact = re.sub(r"[^A-Z0-9]+", "", raw)
    # Tesseract may confuse O/0, I/1 and B/8 on TV graphics.
    normalized = (
        compact
        .replace("0", "O")
        .replace("1", "I")
        .replace("8", "B")
    )
    candidates = (compact, normalized)
    for value in candidates:
        if "OTTCLUB" in value:
            return True
        # Allow one common OCR miss while keeping the match specific to OTTCLUB.
        if re.search(r"OTTCL[UVI]B", value):
            return True
        if re.search(r"OTTC[L1I]UB", value):
            return True
    return bool(re.search(r"\b[O0]TT\s*[-_. ]?\s*CL[UVI]B\b", raw))


async def _quick_ottclub_probe(item: dict):
    cid = str(item.get("id") or "")
    url = str(item.get("url") or "")
    if not cid or not url.startswith(("http://", "https://")) or cid in _ottclub_quick_inflight:
        return
    _ottclub_quick_inflight.add(cid)
    proc = None
    try:
        width, height = 640, 360
        frame_size = width * height
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", url,
            "-vf", f"fps=1,scale={width}:{height},format=gray",
            "-frames:v", "1",
            "-f", "rawvideo", "pipe:1",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        if len(stdout) < frame_size:
            return
        text = await _ocr_ottclub_frame(stdout[:frame_size], width, height)
        hit = _ottclub_text_hit(text)
        now = int(time.time())
        state = dict(_ottclub_ad_state.get(cid) or {})
        state["last_probe"] = now
        state["hits"] = 1 if hit else 0
        state["ocr_text"] = re.sub(r"\s+", " ", str(text or "")).strip()[:500]
        state["error"] = ""
        if hit:
            if not bool(state.get("active")):
                _ottclub_stats["detections"] = int(_ottclub_stats.get("detections") or 0) + 1
            state["active"] = True
            state["last_match"] = now
            state["positive_streak"] = max(1, int(state.get("positive_streak") or 0))
            state["negative_streak"] = 0
        else:
            # A single quick negative frame is not enough to clear an active ad.
            # The existing full 3-frame watcher remains responsible for clearing it.
            if not bool(state.get("active")):
                state["negative_streak"] = int(state.get("negative_streak") or 0) + 1
        _ottclub_ad_state[cid] = state
        _ottclub_stats["probes"] = int(_ottclub_stats.get("probes") or 0) + 1
        _ottclub_stats["last_probe"] = now
        _ottclub_stats["last_channel_id"] = cid
        _ottclub_stats["last_hits"] = 1 if hit else 0
        _ottclub_stats["last_text"] = state["ocr_text"]
    except Exception:
        _ottclub_stats["errors"] = int(_ottclub_stats.get("errors") or 0) + 1
    finally:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        _ottclub_quick_inflight.discard(cid)


async def _server_burned_ad_probe(item: dict) -> dict:
    cid = str(item.get("id") or "")
    url = str(item.get("url") or "")
    result = {
        "ok": False, "score": 0, "samples": 0, "error": "",
        "ottclub_hits": 0, "ottclub_detected": False,
        "cinerama_hits": 0, "cinerama_detected": False, "ocr_text": "",
    }
    if not cid or not url.startswith(("http://", "https://")):
        result["error"] = "bad channel"
        return result

    width, height = 640, 360
    frame_size = width * height
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", url,
        "-vf", f"fps=1,scale={width}:{height},format=gray",
        "-frames:v", "3",
        "-f", "rawvideo", "pipe:1",
    ]
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=14)
        frames = [
            stdout[i:i + frame_size]
            for i in range(0, len(stdout) - frame_size + 1, frame_size)
        ][:3]
        if len(frames) < 2:
            result["error"] = ("too_few_frames " + str(len(frames)) + " " + stderr.decode("utf-8", "ignore")[:80]).strip()
            return result

        sample_step = 80
        diffs = []
        brightness = []
        sampled_frames = [frame[::sample_step] for frame in frames]
        for frame in sampled_frames:
            brightness.append(sum(frame) / (max(1, len(frame)) * 255.0))
        for a, b in zip(sampled_frames, sampled_frames[1:]):
            pairs = min(len(a), len(b))
            diffs.append(sum(abs(a[i] - b[i]) for i in range(pairs)) / (max(1, pairs) * 255.0))
        avg_diff = sum(diffs) / max(1, len(diffs))
        cut_rate = sum(1 for x in diffs if x >= 0.18) / max(1, len(diffs))
        mean_br = sum(brightness) / len(brightness)
        brightness_var = (sum((x - mean_br) ** 2 for x in brightness) / len(brightness)) ** 0.5
        score = round(max(0.0, min(100.0,
            min(1.0, cut_rate / 0.45) * 65.0
            + min(1.0, avg_diff / 0.22) * 25.0
            + min(1.0, brightness_var / 0.16) * 10.0
        )))

        texts = await asyncio.gather(*(_ocr_ottclub_frame(frame, width, height) for frame in frames))
        hits = sum(1 for text in texts if _ottclub_text_hit(text))
        cinerama_hits = sum(1 for text in texts if _cinerama_text_hit(text))
        compact_text = " | ".join(
            re.sub(r"\s+", " ", str(text or "")).strip()[:180]
            for text in texts if str(text or "").strip()
        )[:500]

        result.update({
            "ok": True,
            "score": int(score),
            "samples": len(frames),
            "cut_rate": round(cut_rate, 3),
            "avg_diff": round(avg_diff, 3),
            "brightness_var": round(brightness_var, 3),
            "ottclub_hits": int(hits),
            "ottclub_detected": bool(hits >= 2),
            "cinerama_hits": int(cinerama_hits),
            "cinerama_detected": bool(cinerama_hits >= 2),
            "ocr_text": compact_text,
        })
        return result
    except asyncio.TimeoutError:
        if proc and proc.returncode is None:
            proc.kill()
            try:
                await proc.communicate()
            except Exception:
                pass
        result["error"] = "ffmpeg_timeout"
        return result
    except Exception as exc:
        result["error"] = str(exc)[:120]
        return result


def _store_server_burned_probe(item: dict, probe: dict):
    now = int(time.time())
    cid = str(item.get("id") or "")
    _burned_ad_stats["server_probes"] = int(_burned_ad_stats.get("server_probes") or 0) + 1
    _burned_ad_stats["server_last_probe"] = now
    _ottclub_stats["probes"] = int(_ottclub_stats.get("probes") or 0) + 1
    _ottclub_stats["last_probe"] = now
    _ottclub_stats["last_channel_id"] = cid
    _ottclub_stats["last_hits"] = int(probe.get("ottclub_hits") or 0)
    _ottclub_stats["last_text"] = str(probe.get("ocr_text") or "")[:500]

    if not probe.get("ok"):
        _burned_ad_stats["server_probe_errors"] = int(_burned_ad_stats.get("server_probe_errors") or 0) + 1
        _ottclub_stats["errors"] = int(_ottclub_stats.get("errors") or 0) + 1
    else:
        _burned_ad_stats["server_last_score"] = int(probe.get("score") or 0)

    _cinerama_stats["probes"] = int(_cinerama_stats.get("probes") or 0) + 1
    _cinerama_stats["last_probe"] = now
    _cinerama_stats["last_channel_id"] = cid
    _cinerama_stats["last_hits"] = int(probe.get("cinerama_hits") or 0)

    cstate = dict(_cinerama_placeholder_state.get(cid) or {})
    cdetected = bool(probe.get("ok") and probe.get("cinerama_detected"))
    if cdetected:
        cstate["positive_streak"] = int(cstate.get("positive_streak") or 0) + 1
        cstate["negative_streak"] = 0
        if not bool(cstate.get("active")):
            _cinerama_stats["detections"] = int(_cinerama_stats.get("detections") or 0) + 1
        cstate["active"] = True
        cstate["last_match"] = now
    elif probe.get("ok"):
        cstate["positive_streak"] = 0
        cstate["negative_streak"] = int(cstate.get("negative_streak") or 0) + 1
        if int(cstate["negative_streak"]) >= 2:
            cstate["active"] = False
    cstate["hits"] = int(probe.get("cinerama_hits") or 0)
    cstate["last_probe"] = now
    cstate["ocr_text"] = str(probe.get("ocr_text") or "")[:500]
    cstate["error"] = str(probe.get("error") or "")[:120]
    _cinerama_placeholder_state[cid] = cstate
    _cinerama_stats["active_channels"] = sum(
        1 for value in _cinerama_placeholder_state.values()
        if bool((value or {}).get("active"))
    )

    state = dict(_ottclub_ad_state.get(cid) or {})
    detected = bool(probe.get("ok") and probe.get("ottclub_detected"))
    if detected:
        state["positive_streak"] = int(state.get("positive_streak") or 0) + 1
        state["negative_streak"] = 0
        if not bool(state.get("active")):
            _ottclub_stats["detections"] = int(_ottclub_stats.get("detections") or 0) + 1
        state["active"] = True
        state["last_match"] = now
    elif probe.get("ok"):
        state["positive_streak"] = 0
        state["negative_streak"] = int(state.get("negative_streak") or 0) + 1
        if int(state["negative_streak"]) >= 2:
            state["active"] = False
    state["last_probe"] = now
    state["hits"] = int(probe.get("ottclub_hits") or 0)
    state["ocr_text"] = str(probe.get("ocr_text") or "")[:500]
    state["error"] = str(probe.get("error") or "")[:120]
    _ottclub_ad_state[cid] = state

    channels = _burned_ad_stats.setdefault("channels", {})
    current = dict(channels.get(cid) or {})
    current.update({
        "name": str(item.get("name") or "")[:120],
        "country": str(item.get("country") or "")[:8],
        "server_score": int(probe.get("score") or 0),
        "server_samples": int(probe.get("samples") or 0),
        "server_cut_rate": float(probe.get("cut_rate") or 0),
        "server_avg_diff": float(probe.get("avg_diff") or 0),
        "server_brightness_var": float(probe.get("brightness_var") or 0),
        "server_error": str(probe.get("error") or "")[:120],
        "server_seen_at": now,
        "ottclub_hits": int(probe.get("ottclub_hits") or 0),
        "ottclub_detected": bool(detected),
        "ottclub_active": bool(state.get("active")),
        "ottclub_positive_streak": int(state.get("positive_streak") or 0),
        "ottclub_negative_streak": int(state.get("negative_streak") or 0),
        "cinerama_hits": int(probe.get("cinerama_hits") or 0),
        "cinerama_detected": bool(cdetected),
        "cinerama_active": bool(cstate.get("active")),
        "cinerama_negative_streak": int(cstate.get("negative_streak") or 0),
        "seen_at": max(int(current.get("seen_at") or 0), now),
    })
    channels[cid] = current

def _restore_saved_snapshot():
    saved = _load_json(SNAPSHOT_PATH, {})
    state = saved.get("state") if isinstance(saved, dict) else None
    if not isinstance(state, dict):
        return
    rows = state.get("channels")
    if not isinstance(rows, list):
        return
    channels = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            channels[str(row["id"])] = dict(row)
    if not channels:
        return
    _state["channels"] = channels
    _state["last_refresh"] = int(state.get("last_refresh") or saved.get("saved_at") or 0)
    _state["stats"] = dict(state.get("stats") or {})
    _state["error"] = str(state.get("error") or "")[:300]


_restore_saved_snapshot()


def _attrs(line: str) -> dict[str, str]:
    return {k.lower(): v for k, v in re.findall(r'([\w-]+)="([^"]*)"', line)}


def _normalize_name(name: str) -> str:
    s = re.sub(r"\s+", " ", str(name or "").strip().lower())
    s = re.sub(r"\b(hd|full hd|fhd|uhd|4k|1080p|720p|480p|live|tv)\b", " ", s)
    s = re.sub(r"[^\w\u0400-\u04FF\u0530-\u058F]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _epg_name_variants(value: str) -> list[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return []
    out = [normalized]
    short = re.sub(r"^(?:am|ru|ua|by|kz|uz|md|ge)\s+", "", normalized).strip()
    if short and short not in out:
        out.append(short)
    # Providers often disagree only on spacing around digits/words:
    # "Россия 24" vs "Россия24", "5 Канал" vs "5канал".
    # Use this compact form only for reasonably distinctive names.
    for base in list(out):
        compact = re.sub(r"\s+", "", base)
        if len(compact) >= 5 and compact not in out:
            out.append(compact)
    return out


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


def _parse_epg_xml(text: str) -> tuple[dict, dict, dict, dict]:
    programmes = {}
    names = {}
    logos = {}
    logo_names = {}
    if not text or "<tv" not in text[:5000]:
        return programmes, names, logos, logo_names
    try:
        root = ET.fromstring(text)
    except Exception:
        return programmes, names, logos, logo_names

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
            for variant in _epg_name_variants(display):
                names.setdefault(variant, cid)

        icon = ch.find("icon")
        icon_src = str(icon.attrib.get("src") or "").strip() if icon is not None else ""
        if icon_src.startswith(("http://", "https://")):
            logos.setdefault(cid, icon_src)
            for display in aliases:
                for variant in _epg_name_variants(display):
                    logo_names.setdefault(variant, icon_src)

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
    return programmes, names, logos, logo_names


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
        all_logos = {}
        all_logo_names = {}
        parsed_feeds = await asyncio.gather(
            *[asyncio.to_thread(_parse_epg_xml, text) for text in texts]
        )
        for programmes, names, logos, logo_names in parsed_feeds:
            for cid, rows in programmes.items():
                all_programmes.setdefault(cid, []).extend(rows)
            for key, value in names.items():
                all_names.setdefault(key, value)
            for key, value in logos.items():
                all_logos.setdefault(key, value)
            for key, value in logo_names.items():
                all_logo_names.setdefault(key, value)
        for rows in all_programmes.values():
            rows.sort(key=lambda x: x["start"])
        _state["epg"] = all_programmes
        _state["epg_names"] = all_names
        _state["epg_logos"] = all_logos
        _state["epg_logo_names"] = all_logo_names
        _state["epg_last_refresh"] = int(time.time())
        _state["epg_error"] = ""
    except Exception as exc:
        _state["epg_error"] = repr(exc)[:300]


def _epg_logo_for_channel(item: dict) -> str:
    cid = str(item.get("tvg_id") or "").strip()
    if cid:
        logo = str((_state.get("epg_logos") or {}).get(cid) or "").strip()
        if logo:
            return logo
        base_cid = cid.split("@", 1)[0].strip()
        logo = str((_state.get("epg_logos") or {}).get(base_cid) or "").strip()
        if logo:
            return logo
    aliases = [item.get("name") or ""] + list(item.get("epg_aliases") or [])
    logo_names = _state.get("epg_logo_names") or {}
    matched = set()
    for alias in aliases:
        variants = []
        for variant in _epg_name_variants(alias):
            if variant not in variants:
                variants.append(variant)
        for variant in _logo_name_variants(alias):
            if variant not in variants:
                variants.append(variant)
        for variant in variants:
            logo = str(logo_names.get(variant) or "").strip()
            if logo:
                matched.add(logo)
    # Ambiguity-safe: only use name fallback when all matching aliases agree.
    if len(matched) == 1:
        return next(iter(matched))
    return ""


def _epg_for_channel(item: dict) -> tuple[dict | None, dict | None]:
    cid = str(item.get("tvg_id") or "").strip()
    rows = _state["epg"].get(cid) if cid else None
    if not rows and cid:
        base_cid = cid.split("@", 1)[0].strip()
        rows = _state["epg"].get(base_cid) if base_cid else None
    if not rows:
        aliases = [item.get("name") or ""] + list(item.get("epg_aliases") or [])
        for alias in aliases:
            for variant in _epg_name_variants(alias):
                mapped = _state["epg_names"].get(variant)
                if mapped:
                    rows = _state["epg"].get(mapped)
                    if rows:
                        break
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


def _logo_name_variants(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []

    raw_variants = [raw]

    # Remove only provider metadata/copy suffixes; keep the channel name itself.
    cleaned = re.sub(r"\[[^\]]*(?:not\s*24/?7|geo[- ]?blocked|offline|backup)[^\]]*\]", " ", raw, flags=re.I)
    cleaned = re.sub(r"\((?:\d{3,4}p|\d{3,4}i|hd|fhd|uhd|sd)\)", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*\((?:\d+)\)\s*$", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*\|.*$", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned != raw:
        raw_variants.append(cleaned)

    variants = []
    for source in raw_variants:
        base = _normalize_name(source)
        if not base:
            continue
        if base not in variants:
            variants.append(base)

        compact = re.sub(r"\b(?:телеканал|канал)\b", " ", base, flags=re.I)
        compact = re.sub(r"\s+", " ", compact).strip()
        if compact and compact not in variants:
            variants.append(compact)

        # "ТК 21" / "ТВ 21" are often listed simply as "ТВ21".
        tk_tv = re.sub(r"\bтк\b", "тв", compact, flags=re.I)
        tk_tv = re.sub(r"\s+", "", tk_tv)
        if tk_tv and tk_tv not in variants:
            variants.append(tk_tv)

        joined = re.sub(r"\s+", "", compact)
        if len(joined) >= 4 and joined not in variants:
            variants.append(joined)

    return variants


def _parse_logo_id_catalog_m3u(text: str) -> tuple[dict[str, str], dict[str, str]]:
    by_id = {}
    by_name = {}
    if not text or "#EXTM3U" not in text[:4096]:
        return by_id, by_name
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("#EXTINF"):
            continue
        m_logo = re.search(r'tvg-logo="([^"]+)"', line, flags=re.I)
        if not m_logo:
            continue
        logo = str(m_logo.group(1) or "").strip()
        if not logo.startswith(("http://", "https://")):
            continue
        m_id = re.search(r'tvg-id="([^"]+)"', line, flags=re.I)
        if m_id:
            tvg_id = str(m_id.group(1) or "").strip().lower()
            if tvg_id:
                by_id.setdefault(tvg_id, logo)
        name = line.split(",", 1)[1].strip() if "," in line else ""
        for variant in _logo_name_variants(name):
            by_name.setdefault(variant, logo)
    return by_id, by_name


def _parse_logo_catalog_m3u(text: str) -> dict[str, str]:
    """Return normalized channel-name -> logo URL from an M3U used only as a logo catalogue."""
    out = {}
    if not text or "#EXTM3U" not in text[:4096]:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("#EXTINF"):
            continue
        m_logo = re.search(r'tvg-logo="([^"]+)"', line, flags=re.I)
        if not m_logo:
            continue
        logo = str(m_logo.group(1) or "").strip()
        if not logo.startswith(("http://", "https://")):
            continue
        name = line.split(",", 1)[1].strip() if "," in line else ""
        for normalized in _logo_name_variants(name):
            if normalized and normalized not in out:
                out[normalized] = logo
    return out


def _tvlogo_slug(value: str) -> str:
    s = str(value or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    s = re.sub(r"\s*\|.*$", "", s)
    translit = str.maketrans({
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh","з":"z","и":"i","й":"y",
        "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
        "ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    })
    s = s.translate(translit).replace("+", " plus ")
    s = re.sub(r"\b(?:tv|hd|fhd|uhd|live)\b", " ", s, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _parse_tvlogo_manifest(text: str) -> dict[str, dict[str, str]]:
    out = {"RU": {}, "UA": {}}
    try:
        data = json.loads(text) if text else {}
    except Exception:
        return out
    country_map = {"russia": "RU", "ukraine": "UA"}
    for row in data.get("logos") or []:
        if not isinstance(row, dict):
            continue
        code = country_map.get(str(row.get("country") or "").lower())
        path = str(row.get("path") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code or not path or not name:
            continue
        base = re.sub(r"-(?:ru|ua)\.png$", "", name, flags=re.I)
        base = re.sub(r"-(?:hd|fhd|uhd)$", "", base, flags=re.I)
        if base:
            out[code].setdefault(base, TV_LOGO_MANIFEST_BASE + path)
    return out


async def _discover_iptv_org_api(session: aiohttp.ClientSession) -> tuple[list[dict], dict]:
    """Discover current public streams and the full iptv-org logo catalogue."""
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
        full_logo_catalog = {"by_id": {}, "by_country": {}, "global": {}, "slug": {}}
        for cid, m in meta.items():
            logo = logo_map.get(cid)
            if not logo:
                continue
            full_logo_catalog["by_id"][cid.lower()] = logo
            country = str(m.get('country') or '').upper()
            aliases = [m.get('name'), *(m.get('alt_names') or []), m.get('network')]
            for alias in aliases:
                for variant in _logo_name_variants(alias or ''):
                    if country:
                        full_logo_catalog["by_country"].setdefault((country, variant), set()).add(logo)
                    full_logo_catalog["global"].setdefault(variant, set()).add(logo)
                slug = _tvlogo_slug(alias or '')
                if slug and slug not in {"tv", "vse-tv", "sport", "kino", "music", "muzika"}:
                    full_logo_catalog["slug"].setdefault(slug, set()).add(logo)

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
        return out, full_logo_catalog
    except Exception:
        return [], {"by_id": {}, "by_country": {}, "global": {}, "slug": {}}


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
                fetched, discovered_payload, ru_logo_catalog_text, ru_logo_id_catalog_text, free_tv_logo_texts, tvlogo_manifest_text = await asyncio.gather(
                    asyncio.gather(*[_fetch_text(session, url) for _, url in SOURCE_URLS]),
                    _discover_iptv_org_api(session),
                    _fetch_text(session, RU_LOGO_CATALOG_URL),
                    _fetch_text(session, RU_LOGO_ID_CATALOG_URL),
                    asyncio.gather(*[_fetch_text(session, url) for url in FREE_TV_LOGO_CATALOG_URLS.values()]),
                    _fetch_text(session, TV_LOGO_MANIFEST_URL),
                )
                discovered_api, iptv_org_logo_catalog = discovered_payload
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
                logo_by_global_name = {}
                for x in discovered_api:
                    logo = str(x.get('logo') or '').strip()
                    if not logo:
                        continue
                    tvg_id = str(x.get('tvg_id') or '').strip().lower()
                    if tvg_id and tvg_id not in logo_by_id:
                        logo_by_id[tvg_id] = logo
                    base_tvg_id = tvg_id.split("@", 1)[0].strip() if tvg_id else ""
                    if base_tvg_id and base_tvg_id not in logo_by_id:
                        logo_by_id[base_tvg_id] = logo
                    aliases = [x.get('name') or ''] + list(x.get('epg_aliases') or [])
                    for alias in aliases:
                        for normalized in _logo_name_variants(alias):
                            nkey = (str(x.get('country') or '').upper(), normalized)
                            if normalized and nkey not in logo_by_name:
                                logo_by_name[nkey] = logo
                            if normalized:
                                logo_by_global_name.setdefault(normalized, set()).add(logo)
                enriched_logos = 0
                ru_logo_catalog = _parse_logo_catalog_m3u(ru_logo_catalog_text)
                ru_logo_id_by_id, ru_logo_id_by_name = _parse_logo_id_catalog_m3u(ru_logo_id_catalog_text)
                free_tv_logo_catalogs = {}
                for country, text in zip(FREE_TV_LOGO_CATALOG_URLS.keys(), free_tv_logo_texts):
                    by_id, by_name = _parse_logo_id_catalog_m3u(text)
                    free_tv_logo_catalogs[country] = {"by_id": by_id, "by_name": by_name}
                tvlogo_manifest = _parse_tvlogo_manifest(tvlogo_manifest_text)
                ru_logo_catalog_matches = 0
                ru_logo_id_catalog_matches = 0
                free_tv_logo_matches = 0
                tvlogo_manifest_matches = 0
                country_order = {code: i for i, code in enumerate(("AM","RU","GE","UA","BY","KZ","UZ","MD"))}
                for item in candidates:
                    item['adult'] = bool(item.get('adult')) or _is_adult_channel(item)
                    if not str(item.get('logo') or '').strip():
                        tvg_id = str(item.get('tvg_id') or '').strip().lower()
                        full_by_id = iptv_org_logo_catalog.get("by_id") or {}
                        logo = (logo_by_id.get(tvg_id) or full_by_id.get(tvg_id)) if tvg_id else None
                        if not logo and tvg_id:
                            base_tvg_id = tvg_id.split("@", 1)[0].strip()
                            if base_tvg_id:
                                logo = logo_by_id.get(base_tvg_id) or full_by_id.get(base_tvg_id)
                        if not logo:
                            country = str(item.get('country') or '').upper()
                            country_matches = {
                                logo_by_name.get((country, v))
                                for v in _logo_name_variants(item.get('name') or '')
                                if logo_by_name.get((country, v))
                            }
                            country_matches.discard(None)
                            if len(country_matches) == 1:
                                logo = next(iter(country_matches))
                        if not logo:
                            full_by_country = iptv_org_logo_catalog.get("by_country") or {}
                            full_country_matches = set()
                            for v in _logo_name_variants(item.get('name') or ''):
                                full_country_matches.update(full_by_country.get((country, v)) or set())
                            if len(full_country_matches) == 1:
                                logo = next(iter(full_country_matches))
                        if not logo:
                            global_matches = set()
                            for v in _logo_name_variants(item.get('name') or ''):
                                global_matches.update(logo_by_global_name.get(v) or set())
                            if len(global_matches) == 1:
                                logo = next(iter(global_matches))
                        if not logo:
                            full_global = iptv_org_logo_catalog.get("global") or {}
                            full_global_matches = set()
                            for v in _logo_name_variants(item.get('name') or ''):
                                full_global_matches.update(full_global.get(v) or set())
                            if len(full_global_matches) == 1:
                                logo = next(iter(full_global_matches))
                        if not logo:
                            slug = _tvlogo_slug(item.get('name') or '')
                            if slug and slug not in {"tv", "vse-tv", "sport", "kino", "music", "muzika"}:
                                slug_matches = (iptv_org_logo_catalog.get("slug") or {}).get(slug) or set()
                                if len(slug_matches) == 1:
                                    logo = next(iter(slug_matches))
                        if not logo:
                            country = str(item.get('country') or '').upper()
                            catalog = free_tv_logo_catalogs.get(country) or {}
                            by_id = catalog.get('by_id') or {}
                            by_name = catalog.get('by_name') or {}
                            base_tvg_id = tvg_id.split("@", 1)[0].strip() if tvg_id else ""
                            logo = by_id.get(tvg_id) if tvg_id else None
                            if not logo and base_tvg_id:
                                logo = by_id.get(base_tvg_id)
                            if not logo:
                                matches = {
                                    by_name.get(v)
                                    for v in _logo_name_variants(item.get('name') or '')
                                    if by_name.get(v)
                                }
                                matches.discard(None)
                                if len(matches) == 1:
                                    logo = next(iter(matches))
                            if logo:
                                free_tv_logo_matches += 1
                        if not logo:
                            country = str(item.get('country') or '').upper()
                            manifest_country = tvlogo_manifest.get(country) or {}
                            slug = _tvlogo_slug(item.get('name') or '')
                            if slug:
                                logo = manifest_country.get(slug)
                            if logo:
                                tvlogo_manifest_matches += 1
                        if not logo and str(item.get('country') or '').upper() == 'RU':
                            sw_id = tvg_id.split("@", 1)[0].strip() if tvg_id else ""
                            logo = ru_logo_id_by_id.get(tvg_id) if tvg_id else None
                            if not logo and sw_id:
                                logo = ru_logo_id_by_id.get(sw_id)
                            if not logo:
                                sw_matches = {
                                    ru_logo_id_by_name.get(v)
                                    for v in _logo_name_variants(item.get('name') or '')
                                    if ru_logo_id_by_name.get(v)
                                }
                                sw_matches.discard(None)
                                if len(sw_matches) == 1:
                                    logo = next(iter(sw_matches))
                            if logo:
                                ru_logo_id_catalog_matches += 1
                        if not logo and str(item.get('country') or '').upper() == 'RU':
                            matched = {
                                ru_logo_catalog.get(v)
                                for v in _logo_name_variants(item.get('name') or '')
                                if ru_logo_catalog.get(v)
                            }
                            matched.discard(None)
                            # Use the fallback only when all matching variants point
                            # to exactly one logo. This avoids wrong logos on aliases.
                            if len(matched) == 1:
                                logo = next(iter(matched))
                                ru_logo_catalog_matches += 1
                        if logo:
                            item['logo'] = logo
                            enriched_logos += 1
                unusable_filtered = sum(1 for x in candidates if _hide_unusable_catalog_channel(x))
                wink_streams_filtered = sum(1 for x in candidates if _is_wink_placeholder_stream(x))
                candidates = [
                    x for x in candidates
                    if not _hide_unusable_catalog_channel(x)
                    and not _is_wink_placeholder_stream(x)
                ]

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

                merged_aliases = []
                for x in rows:
                    for alias in [x.get("name"), *(x.get("epg_aliases") or [])]:
                        alias = str(alias or "").strip()
                        if alias and alias not in merged_aliases:
                            merged_aliases.append(alias)
                if merged_aliases:
                    primary["epg_aliases"] = merged_aliases[:24]

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
                "ru_logo_catalog_entries": len(ru_logo_catalog),
                "ru_logo_catalog_matches": ru_logo_catalog_matches,
                "ru_logo_id_catalog_entries": len(ru_logo_id_by_id),
                "ru_logo_id_catalog_matches": ru_logo_id_catalog_matches,
                "free_tv_logo_catalogs": len(free_tv_logo_catalogs),
                "free_tv_logo_matches": free_tv_logo_matches,
                "tvlogo_manifest_matches": tvlogo_manifest_matches,
                "unusable_catalog_filtered": unusable_filtered,
                "wink_streams_filtered": wink_streams_filtered,
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
        if not str(row.get("logo") or "").strip():
            epg_logo = _epg_logo_for_channel(row)
            if epg_logo:
                row["logo"] = epg_logo
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
    stats["epg_logo_channels"] = len(_state.get("epg_logos") or {})
    stats["epg_source_count"] = len(EPG_URLS)
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
    missing_logo_samples = [
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "country": x.get("country"),
            "tvg_id": x.get("tvg_id"),
            "group": x.get("group"),
            "epg_aliases": list(x.get("epg_aliases") or [])[:6],
        }
        for x in rows if not str(x.get("logo") or "").strip()
    ][:180]
    recent_failovers = sorted(
        [x for x in rows if int(x.get("last_failover") or 0) > 0],
        key=lambda x: int(x.get("last_failover") or 0),
        reverse=True,
    )[:50]
    history = _load_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    ad_history = _load_json(AD_HISTORY_PATH, [])
    if not isinstance(ad_history, list):
        ad_history = []
    ad_starts = [x for x in ad_history if isinstance(x, dict) and bool(x.get("active"))]
    return web.json_response({
        "ok": True,
        "stats": state.get("stats") or {},
        "missing_logo_samples": missing_logo_samples,
        "scan_history": history[-48:],
        "ad_detection": {
            "events": ad_history[-100:],
            "starts_total": len(ad_starts),
            "channels_seen": len({str(x.get("channel_id") or "") for x in ad_starts if x.get("channel_id")}),
            "last_event": ad_history[-1] if ad_history else None,
            "scanner": dict(_ad_scan_stats),
            "burned_in_observer": {
                "samples": int(_burned_ad_stats.get("samples") or 0),
                "channels_seen": len(_burned_ad_stats.get("channels") or {}),
                "high_score_count": int(_burned_ad_stats.get("high_score_count") or 0),
                "last_score": int(_burned_ad_stats.get("last_score") or 0),
                "last_channel_id": str(_burned_ad_stats.get("last_channel_id") or ""),
                "last_seen": int(_burned_ad_stats.get("last_seen") or 0),
                "last_free_play": int(_burned_ad_stats.get("last_free_play") or 0),
                "last_free_play_channel_id": str(_burned_ad_stats.get("last_free_play_channel_id") or ""),
                "server_probes": int(_burned_ad_stats.get("server_probes") or 0),
                "server_probe_errors": int(_burned_ad_stats.get("server_probe_errors") or 0),
                "server_last_probe": int(_burned_ad_stats.get("server_last_probe") or 0),
                "server_last_score": int(_burned_ad_stats.get("server_last_score") or 0),
                "observer_expected": bool(
                    int(_burned_ad_stats.get("last_free_play") or 0)
                    and int(_burned_ad_stats.get("last_free_play") or 0) > int(_burned_ad_stats.get("last_seen") or 0)
                ),
                "channels": sorted(
                    list((_burned_ad_stats.get("channels") or {}).values()),
                    key=lambda x: int((x or {}).get("score") or 0),
                    reverse=True,
                )[:20],
                "mode": "observe_only",
            },
            "cinerama_placeholder": {
                "probes": int(_cinerama_stats.get("probes") or 0),
                "detections": int(_cinerama_stats.get("detections") or 0),
                "active_channels": int(_cinerama_stats.get("active_channels") or 0),
                "last_channel_id": str(_cinerama_stats.get("last_channel_id") or ""),
                "last_hits": int(_cinerama_stats.get("last_hits") or 0),
                "last_probe": int(_cinerama_stats.get("last_probe") or 0),
                "mode": "temporary_overlay_auto_recheck",
            },
            "ottclub_detector": {
                "probes": int(_ottclub_stats.get("probes") or 0),
                "errors": int(_ottclub_stats.get("errors") or 0),
                "detections": int(_ottclub_stats.get("detections") or 0),
                "last_probe": int(_ottclub_stats.get("last_probe") or 0),
                "last_channel_id": str(_ottclub_stats.get("last_channel_id") or ""),
                "last_hits": int(_ottclub_stats.get("last_hits") or 0),
                "last_text": str(_ottclub_stats.get("last_text") or "")[:500],
                "active_channels": [
                    cid for cid, value in _ottclub_ad_state.items()
                    if bool((value or {}).get("active"))
                ][:20],
                "mode": "replace_only_ottclub",
            },
            "marker_detection_supported": bool((_ad_scan_stats.get("tag_counts") or {})),
        },
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
        worker_mode = str(os.getenv("IPTV_BACKGROUND_ENABLED", "1")).strip().lower() in {"0", "false", "no", "off"}
        if worker_mode:
            _worker_control["refresh_requested_at"] = int(time.time())
        else:
            await refresh_channels()
    compact = request.query.get("compact") == "1"
    if compact:
        now = time.monotonic()
        cache_key = (
            int(_state.get("last_refresh") or 0),
            int(_state.get("epg_last_refresh") or 0),
            str(_state.get("error") or ""),
            str(_state.get("epg_error") or ""),
        )
        if _compact_response_cache["key"] == cache_key and now < float(_compact_response_cache["expires_at"] or 0) and _compact_response_cache["body"]:
            return web.Response(
                body=_compact_response_cache["body"],
                content_type="application/json",
                charset="utf-8",
                headers={"Cache-Control": "no-store"},
            )
        payload = public_state(compact=True)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _compact_response_cache.update({"key": cache_key, "body": body, "expires_at": now + 5.0})
        return web.Response(body=body, content_type="application/json", charset="utf-8", headers={"Cache-Control": "no-store"})
    return web.json_response(public_state(compact=False), headers={"Cache-Control": "no-store"})


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


async def api_ad_viewing(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    cid = str((body or {}).get("channel_id") or "").strip()
    item = _state["channels"].get(cid)
    if not item or item.get("status") != "ONLINE":
        return web.json_response({"ok": False, "error": "unknown channel"}, status=404)
    _burned_ad_stats["last_free_play"] = int(time.time())
    _burned_ad_stats["last_free_play_channel_id"] = cid
    ott = dict(_ottclub_ad_state.get(cid) or {})
    if int(time.time()) - int(ott.get("last_probe") or 0) >= 2:
        asyncio.create_task(_quick_ottclub_probe(item))
    if int(time.time()) - int(ott.get("last_probe") or 0) >= 2:
        asyncio.create_task(_quick_ottclub_probe(item))
    return web.json_response({"ok": True}, headers={"Cache-Control": "no-store"})


async def api_ad_state(request):
    cid = str(request.query.get("id") or "").strip()
    item = _state["channels"].get(cid)
    if not item:
        return web.json_response({"ok": False, "active": False, "error": "unknown channel"}, status=404)
    _burned_ad_stats["last_free_play"] = int(time.time())
    _burned_ad_stats["last_free_play_channel_id"] = cid
    ott = dict(_ottclub_ad_state.get(cid) or {})
    cin = dict(_cinerama_placeholder_state.get(cid) or {})
    try:
        host = (urlparse(str(item.get("url") or "")).hostname or "").lower()
    except Exception:
        host = ""
    cinerama_host = host == "cinerama.uz" or host.endswith(".cinerama.uz")
    active = bool(ott.get("active") or cin.get("active") or cinerama_host)
    reason = "cinerama_host" if cinerama_host else ("cinerama_placeholder" if bool(cin.get("active")) else ("ottclub" if bool(ott.get("active")) else ""))
    return web.json_response({
        "ok": True,
        "active": active,
        "reason": reason,
        "ottclub_active": bool(ott.get("active")),
        "ottclub_hits": int(ott.get("hits") or 0),
        "cinerama_active": bool(cin.get("active") or cinerama_host),
        "cinerama_host": bool(cinerama_host),
        "cinerama_hits": int(cin.get("hits") or 0),
        "checked_at": float(max(ott.get("last_probe") or 0, cin.get("last_probe") or 0)),
    }, headers={"Cache-Control": "no-store"})


async def api_ad_visual_observe(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad json"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "bad body"}, status=400)

    cid = str(body.get("channel_id") or "").strip()
    item = _state["channels"].get(cid)
    if not item:
        return web.json_response({"ok": False, "error": "unknown channel"}, status=404)

    # This observer is intentionally Free-only. Personal/Edem playback is never
    # sampled by the burned-in ad experiment.
    if bool(item.get("personal")):
        return web.json_response({"ok": False, "error": "not supported"}, status=400)

    now = time.time()
    last = float(_burned_ad_last_report.get(cid) or 0)
    if now - last < 8.0:
        return web.json_response({"ok": True, "ignored": True}, headers={"Cache-Control": "no-store"})

    try:
        score = max(0, min(100, int(round(float(body.get("score") or 0)))))
        cut_rate = max(0.0, min(1.0, float(body.get("cut_rate") or 0)))
        avg_diff = max(0.0, min(1.0, float(body.get("avg_diff") or 0)))
        brightness_var = max(0.0, min(1.0, float(body.get("brightness_var") or 0)))
        samples = max(0, min(60, int(body.get("samples") or 0)))
        observer_error = str(body.get("observer_error") or "").strip()[:160]
        observer_state = str(body.get("observer_state") or "").strip()[:40]
    except Exception:
        return web.json_response({"ok": False, "error": "bad values"}, status=400)

    _burned_ad_last_report[cid] = now
    if samples > 0:
        _burned_ad_stats["samples"] = int(_burned_ad_stats.get("samples") or 0) + 1
    _burned_ad_stats["last_score"] = score
    _burned_ad_stats["last_channel_id"] = cid
    _burned_ad_stats["last_seen"] = int(now)
    if score >= 70:
        _burned_ad_stats["high_score_count"] = int(_burned_ad_stats.get("high_score_count") or 0) + 1

    channels = _burned_ad_stats.setdefault("channels", {})
    channels[cid] = {
        "name": str(item.get("name") or "")[:120],
        "country": str(item.get("country") or "")[:8],
        "score": score,
        "cut_rate": round(cut_rate, 3),
        "avg_diff": round(avg_diff, 3),
        "brightness_var": round(brightness_var, 3),
        "samples": samples,
        "observer_error": observer_error,
        "observer_state": observer_state,
        "seen_at": int(now),
    }
    if len(channels) > 80:
        oldest = sorted(channels.items(), key=lambda kv: int((kv[1] or {}).get("seen_at") or 0))[:-80]
        for key, _ in oldest:
            channels.pop(key, None)

    return web.json_response({"ok": True, "score": score}, headers={"Cache-Control": "no-store"})


async def api_play(request):
    cid = request.query.get("id", "")
    item = _state["channels"].get(cid)
    if not item or item.get("status") != "ONLINE":
        raise web.HTTPNotFound(text="Channel unavailable")

    _burned_ad_stats["last_free_play"] = int(time.time())
    _burned_ad_stats["last_free_play_channel_id"] = str(cid or "")

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

    async def ad_watch_loop():
        await asyncio.sleep(10)
        cursor = 0
        hls_scan_last = 0.0
        while True:
            try:
                now = time.time()
                rows = [x for x in _state["channels"].values() if x.get("status") == "ONLINE"]
                if rows and now - hls_scan_last >= 30:
                    hls_scan_last = now
                    batch = []
                    for _ in range(min(12, len(rows))):
                        batch.append(rows[cursor % len(rows)])
                        cursor += 1
                    sem = asyncio.Semaphore(3)
                    async def probe_one(item):
                        async with sem:
                            try:
                                await _free_channel_ad_state(item)
                            except Exception:
                                pass
                    await asyncio.gather(*(probe_one(item) for item in batch))
            except Exception:
                pass
            await asyncio.sleep(10)
    app["iptv_ad_watch_task"] = asyncio.create_task(ad_watch_loop())

    async def ottclub_watch_loop():
        await asyncio.sleep(12)
        while True:
            try:
                now = time.time()
                last_play = int(_burned_ad_stats.get("last_free_play") or 0)
                last_cid = str(_burned_ad_stats.get("last_free_play_channel_id") or "")
                if last_cid and last_play and now - last_play <= 180:
                    item = _state["channels"].get(last_cid)
                    if item and item.get("status") == "ONLINE":
                        probe = await _server_burned_ad_probe(item)
                        _store_server_burned_probe(item, probe)
            except Exception:
                pass
            await asyncio.sleep(7)
    app["iptv_ottclub_watch_task"] = asyncio.create_task(ottclub_watch_loop())

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
    for key in ("iptv_task", "iptv_epg_task", "iptv_ad_watch_task", "iptv_ottclub_watch_task"):
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
    app.router.add_post("/api/iptv/ad-viewing", api_ad_viewing)
    app.router.add_get("/api/iptv/ad-state", api_ad_state)
    app.router.add_post("/api/iptv/ad-visual-observe", api_ad_visual_observe)
    app.router.add_get("/api/iptv/proxy", api_proxy)
    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
