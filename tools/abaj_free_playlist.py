#!/usr/bin/env python3
"""Build a standalone, deduplicated M3U from ABAJ TV's public Free sources.

No paid Edo lists, user accounts, API keys, or Railway dependencies.
The source of truth is app/iptv.py on the existing ABAJ TV branch.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

UA = "ABAJ-TV-Free-Playlist/1.0 (+https://github.com/edgar198282-ux/FaceTalkAi)"
LIMIT_BYTES = 12 * 1024 * 1024
MAX_WORKERS = 12
MIN_CHANNELS = 800
TIMEOUT = 13
NET_URL = re.compile(r"^https?://", re.I)


def definitions(path: Path):
    """Extract static lists without executing server code or importing aiohttp."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("SOURCE_URLS", "OFFICIAL_CHANNELS"):
                values[target.id] = ast.literal_eval(node.value)
    sources = values.get("SOURCE_URLS")
    officials = values.get("OFFICIAL_CHANNELS")
    if not isinstance(sources, list) or not isinstance(officials, list):
        raise ValueError("ABAJ TV public source configuration not found")
    unique = []
    used = set()
    for country, url in sources:
        if not NET_URL.match(str(url)) or url in used:
            continue
        used.add(url)
        unique.append((str(country).upper(), str(url)))
    return unique, officials


def fetch_source(item):
    country, url = item
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "text/plain,*/*;q=0.8"}
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(LIMIT_BYTES + 1)
        if len(data) > LIMIT_BYTES:
            raise ValueError("playlist exceeds size limit")
        text = data.decode("utf-8-sig", "replace")
        if not text.lstrip().startswith("#EXTM3U"):
            raise ValueError("response is not an M3U playlist")
        return country, url, text, ""
    except Exception as exc:
        return country, url, "", f"{type(exc).__name__}: {str(exc)[:170]}"


def safe_http(url):
    # HTTP(S) streams only. Never publish file://, udp:// or browser script URLs.
    if not NET_URL.match(url):
        return False
    try:
        u = urlsplit(url)
        return u.scheme.lower() in ("http", "https") and bool(u.hostname) and not u.username
    except ValueError:
        return False


def sanitize(s):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(s or "")).strip()


def safe_attr(s):
    return sanitize(s).replace('"', "'")


def entry(name, url, group, tvg_id="", logo="", attrs=""):
    name = sanitize(name) or "TV"
    url = sanitize(url)
    if not safe_http(url):
        return None
    group = sanitize(group) or "Free"
    if attrs:
        # Keep external metadata, including channel names and logos.
        info = sanitize(attrs)
        if not info.startswith("#EXTINF:") or "," not in info:
            info = ""
        if info and 'group-title="' not in info:
            head, sep, tail = info.rpartition(",")
            info = head + ' group-title="' + safe_attr(group) + '"' + sep + tail
    else:
        info = (
            '#EXTINF:-1 tvg-id="' + safe_attr(tvg_id) +
            '" tvg-logo="' + safe_attr(logo) +
            '" group-title="' + safe_attr(group) + '",' + name
        )
    return info, url


def parse_m3u(text, country):
    selected = None
    for line0 in text.splitlines():
        line = sanitize(line0)
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            selected = line
            continue
        if line.startswith("#"):
            continue
        if not safe_http(line):
            continue
        if selected is None:
            continue
        label = selected.rsplit(",", 1)[-1].strip() or "TV"
        group = country if country != "HQ" else "Free"
        record = entry(label, line, group=group, attrs=selected)
        selected = None
        if record:
            yield record


def build(source_path, output_path, stats_path, previous_path=None):
    sources, official = definitions(source_path)
    ordered = {}
    for item in official:
        if not isinstance(item, dict):
            continue
        record = entry(item.get("name"), item.get("url"),
                       item.get("group") or "General",
                       item.get("tvg_id"), item.get("logo"))
        if record:
            ordered.setdefault(record[1], record)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_source, item) for item in sources]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Stable order despite parallel requests. Prefer original official/curated streams.
    by_url = {url: (country, text, err) for country, url, text, err in results}
    per_source = []
    failed = []
    for country, url in sources:
        country0, body, err = by_url[url]
        if err:
            failed.append({"country": country, "url": url, "error": err})
            continue
        before = len(ordered)
        parsed = 0
        for record in parse_m3u(body, country):
            parsed += 1
            ordered.setdefault(record[1], record)
        per_source.append({"country": country, "url": url, "parsed": parsed,
                           "new": len(ordered) - before})

    total = len(ordered)
    if total < MIN_CHANNELS:
        raise ValueError(f"Only {total} unique streams, below safe minimum {MIN_CHANNELS}; previous file retained")

    # If sources temporarily go offline, don't replace a good playlist with a partial copy.
    if previous_path and previous_path.exists():
        prior = previous_path.read_text(encoding="utf-8", errors="ignore").count("#EXTINF:")
        if prior >= MIN_CHANNELS and total < prior * 0.60:
            raise ValueError(f"New list {total} is under 60% of previous {prior}; previous file retained")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for inf, url in ordered.values():
        lines.extend((inf, url))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    stats = {
        "updated_at_utc": now,
        "unique_channels": total,
        "official_channels": len(official),
        "public_sources": len(sources),
        "successful_sources": len(per_source),
        "failed_sources": len(failed),
        "sources": per_source,
        "failures": failed,
        "note": "Channel presence does not guarantee stream availability. Free public sources only.",
    }
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("sources", "failures")}, ensure_ascii=False))
    if failed:
        print("Failed source downloads:", file=sys.stderr)
        for item in failed[:30]:
            print(f"  {item['url']} => {item['error']}", file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stats", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    return build(args.source, args.output, args.stats, args.previous)


if __name__ == "__main__":
    sys.exit(main())
