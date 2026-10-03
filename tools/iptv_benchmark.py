#!/usr/bin/env python3
import argparse, asyncio, json, re, statistics, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from urllib.parse import urljoin
import aiohttp

DEFAULT_BASE = "https://facetalkai-production.up.railway.app"

def pct(values, q):
    if not values:
        return 0
    v = sorted(values)
    return int(v[min(len(v)-1, round((len(v)-1)*q))])

def first_media_url(text, base):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    variants = []
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 0
            for nxt in lines[i+1:]:
                if not nxt.startswith("#"):
                    variants.append((bw, urljoin(base, nxt)))
                    break
    if variants:
        return max(variants, key=lambda x: x[0])[1], True
    for line in lines:
        if not line.startswith("#"):
            return urljoin(base, line), False
    return "", False

async def read_url(session, url, timeout, limit=131072):
    started = time.perf_counter()
    async with session.get(url, allow_redirects=True, timeout=timeout, headers={"User-Agent":"IPTV-Player/1.0"}) as r:
        body = await r.content.read(limit)
        return r.status, str(r.url), body, int((time.perf_counter()-started)*1000)

async def test_one(session, ch, timeout):
    url = str(ch.get("url") or "")
    out = {"id":ch.get("id"),"name":ch.get("name"),"country":ch.get("country"),"quality":ch.get("quality"),"url":url}
    started = time.perf_counter()
    try:
        status, final, body, m1 = await read_url(session, url, timeout)
        out["manifest_ms"] = m1
        if status not in (200,206) or b"#EXTM3U" not in body[:4096]:
            out.update(ok=False,error=f"manifest_http_{status}")
            return out
        media, is_master = first_media_url(body.decode("utf-8","ignore"), final)
        if not media:
            out.update(ok=False,error="no_media_url")
            return out
        if is_master and media.lower().split("?")[0].endswith(".m3u8"):
            status2, final2, body2, m2 = await read_url(session, media, timeout)
            out["variant_ms"] = m2
            if status2 not in (200,206):
                out.update(ok=False,error=f"variant_http_{status2}")
                return out
            media, _ = first_media_url(body2.decode("utf-8","ignore"), final2)
        if not media:
            out.update(ok=False,error="no_segment")
            return out
        status3, _, seg, m3 = await read_url(session, media, timeout, 65536)
        out["segment_ms"] = m3
        out["segment_bytes"] = len(seg)
        out["total_ms"] = int((time.perf_counter()-started)*1000)
        out["ok"] = status3 in (200,206) and len(seg) > 0
        if not out["ok"]:
            out["error"] = f"segment_http_{status3}"
    except Exception as e:
        out.update(ok=False,error=type(e).__name__,total_ms=int((time.perf_counter()-started)*1000))
    return out

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--countries", default="AM,RU")
    ap.add_argument("--qualities", default="4K,FHD,HD")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    timeout = aiohttp.ClientTimeout(total=args.timeout, connect=min(3,args.timeout), sock_read=args.timeout)
    connector = aiohttp.TCPConnector(limit=args.concurrency, limit_per_host=4, ttl_dns_cache=300, resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
        async with s.get(args.base.rstrip("/")+"/api/iptv/channels?compact=1", headers={"User-Agent":"AbajTV-Benchmark/1.0"}) as r:
            data = await r.json()
        rows = list(data.get("channels") or [])
        countries = {x.strip().upper() for x in args.countries.split(",") if x.strip()}
        qualities = {x.strip().upper() for x in args.qualities.split(",") if x.strip()}
        if not args.all:
            rows = [x for x in rows if str(x.get("country") or "").upper() in countries and str(x.get("quality") or "").upper() in qualities]
        rows.sort(key=lambda x:(0 if str(x.get("country") or "").upper()=="AM" else 1, 0 if str(x.get("quality") or "").upper()=="4K" else 1, str(x.get("name") or "")))
        rows = rows[:max(1,args.limit)]
        sem = asyncio.Semaphore(args.concurrency)
        async def run(ch):
            async with sem:
                return await test_one(s, ch, args.timeout)
        results = await asyncio.gather(*(run(x) for x in rows))

    ok = [x for x in results if x.get("ok")]
    totals = [int(x.get("total_ms") or 0) for x in ok if x.get("total_ms")]
    manifests = [int(x.get("manifest_ms") or 0) for x in ok if x.get("manifest_ms")]
    segments = [int(x.get("segment_ms") or 0) for x in ok if x.get("segment_ms")]
    by_quality = {}
    for q in sorted({str(x.get("quality") or "SD") for x in results}):
        rr = [x for x in results if str(x.get("quality") or "SD")==q]
        qq = [x for x in rr if x.get("ok")]
        vv = [int(x.get("total_ms") or 0) for x in qq if x.get("total_ms")]
        by_quality[q] = {"tested":len(rr),"ok":len(qq),"p50_ms":pct(vv,.5),"p90_ms":pct(vv,.9)}
    summary = {
        "tested":len(results),"ok":len(ok),"success_pct":round(len(ok)*100/len(results),1) if results else 0,
        "manifest_p50_ms":pct(manifests,.5),"manifest_p90_ms":pct(manifests,.9),
        "segment_p50_ms":pct(segments,.5),"segment_p90_ms":pct(segments,.9),
        "startup_p50_ms":pct(totals,.5),"startup_p90_ms":pct(totals,.9),
        "startup_avg_ms":round(statistics.mean(totals)) if totals else 0,
        "by_quality":by_quality,
        "slowest":sorted(ok,key=lambda x:int(x.get("total_ms") or 0),reverse=True)[:15],
        "failures":[x for x in results if not x.get("ok")][:30],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
