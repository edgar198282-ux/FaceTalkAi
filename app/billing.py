from datetime import datetime, timezone
import asyncio
import aiohttp
from .runtime_config import runtime_value

BASE = "https://api.openai.com/v1/organization/costs"

def _start_of_day():
    n = datetime.now(timezone.utc); return int(datetime(n.year, n.month, n.day, tzinfo=timezone.utc).timestamp())

def _start_of_month():
    n = datetime.now(timezone.utc); return int(datetime(n.year, n.month, 1, tzinfo=timezone.utc).timestamp())

async def _fetch(start_time, admin_key, project_id):
    if not admin_key:
        return {"ok": False, "usd": None, "error": "OPENAI_ADMIN_KEY не добавлен"}
    params = {"start_time": str(start_time), "bucket_width": "1d", "limit": "31"}
    if project_id: params["project_ids[]"] = project_id
    headers = {"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"}
    total = 0.0; next_page = None
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                req = dict(params)
                if next_page: req["page"] = next_page
                async with session.get(BASE, params=req, headers=headers) as r:
                    raw = await r.text()
                    if r.status != 200: return {"ok": False, "usd": None, "error": f"HTTP {r.status}: {raw[:180]}"}
                    data = await r.json()
                for bucket in data.get("data", []):
                    for result in bucket.get("results", []):
                        try: total += float((result.get("amount") or {}).get("value", 0) or 0)
                        except Exception: pass
                if not data.get("has_more") or not data.get("next_page"): break
                next_page = data["next_page"]
        return {"ok": True, "usd": total, "error": None}
    except Exception as e:
        return {"ok": False, "usd": None, "error": f"{type(e).__name__}: {str(e)[:160]}"}

async def real_openai_costs():
    admin_key = await runtime_value("OPENAI_ADMIN_KEY")
    project_id = await runtime_value("OPENAI_PROJECT_ID")
    today, month = await asyncio.gather(_fetch(_start_of_day(), admin_key, project_id), _fetch(_start_of_month(), admin_key, project_id))
    return {"today": today, "month": month, "scope": ("project " + project_id) if project_id else "organization"}
