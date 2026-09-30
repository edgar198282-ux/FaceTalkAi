import json
import os
import time
from urllib.parse import quote, urlencode, urlparse

import aiohttp
from aiohttp import web

from .config import DATA_DIR, PORT
from . import iptv
from .db import get_setting, set_setting, list_settings_prefix
from .webapp import (
    api_error_middleware,
    api_me,
    api_admin_stats,
    api_admin_keys,
    api_admin_gpu_health,
    api_admin_video_limit,
    api_photo,
    api_profile_photo,
    api_role,
    api_mode,
    api_reset,
    api_upload_photo,
    api_voice_clone,
    api_delete_voice_clone,
    api_profile_select,
    api_profile_rename,
    api_chat,
    validate_init_data,
    _user_from_request,
    _is_admin_user,
    GEN_DIR,
    WEB_DIR,
    cleanup_generated,
)

APK_DIR = os.path.join(DATA_DIR, 'apk')
APK_PATH = os.path.join(APK_DIR, 'FaceTalkAI-latest.apk')
APK_META_PATH = os.path.join(APK_DIR, 'release.json')
MIN_APK_SIZE = 300_000
PUBLIC_APK_PATH = '/downloads/AbajTV-latest.apk'
os.makedirs(APK_DIR, exist_ok=True)

_edem_cache = {}
_edem_sessions = {}
_edem_stream_tokens = {}


def _read_apk_meta():
    try:
        with open(APK_META_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

async def index(request):
    path = os.path.join(WEB_DIR, 'index.html')
    return web.FileResponse(path, headers={'Cache-Control':'no-store, no-cache, must-revalidate, max-age=0','Pragma':'no-cache'})

async def api_app_release(request):
    meta = _read_apk_meta()
    available = os.path.isfile(APK_PATH) and os.path.getsize(APK_PATH) >= MIN_APK_SIZE
    return web.json_response({'ok':True,'service':'facetalk-ota','available':available,'version_name':str(meta.get('version_name') or ''),'version_code':int(meta.get('version_code') or 0),'size_bytes':os.path.getsize(APK_PATH) if available else 0,'download_url':PUBLIC_APK_PATH if available else '','published_at':meta.get('published_at')}, headers={'Cache-Control':'no-store, max-age=0'})

async def api_app_download(request):
    if not os.path.isfile(APK_PATH) or os.path.getsize(APK_PATH) < MIN_APK_SIZE:
        raise web.HTTPNotFound(text='APK not published yet')
    return web.FileResponse(
        APK_PATH,
        headers={
            'Content-Type':'application/vnd.android.package-archive',
            'Content-Disposition':'attachment; filename="AbajTV-latest.apk"',
            'Cache-Control':'no-store, max-age=0',
            'X-Content-Type-Options':'nosniff',
        },
    )

def _valid_deploy_token(supplied):
    import hmac
    supplied=(supplied or '').strip()
    if not supplied: return False
    candidates=[(os.getenv('FACETALK_APK_DEPLOY_TOKEN') or '').strip(), (os.getenv('INTERNAL_API_SECRET') or '').strip()]
    return any(v and hmac.compare_digest(supplied, v) for v in candidates)

async def api_app_upload(request):
    supplied = (request.headers.get('X-FaceTalk-Deploy-Token') or '').strip()
    configured = bool((os.getenv('FACETALK_APK_DEPLOY_TOKEN') or '').strip() or (os.getenv('INTERNAL_API_SECRET') or '').strip())
    if not configured or not _valid_deploy_token(supplied): return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    raw = await request.read()
    if len(raw) < MIN_APK_SIZE or not raw.startswith(b'PK'): return web.json_response({'ok':False,'error':'invalid apk'}, status=400)
    version_name = (request.headers.get('X-FaceTalk-App-Version') or '').strip() or '1.0.0'
    try: version_code = int(request.headers.get('X-FaceTalk-App-Version-Code') or '0')
    except Exception: version_code = 0
    if version_code <= 0: return web.json_response({'ok':False,'error':'invalid version code'}, status=400)
    tmp = APK_PATH + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, APK_PATH)
    meta={'version_name':version_name,'version_code':version_code,'size_bytes':len(raw),'published_at':int(time.time())}
    with open(APK_META_PATH+'.tmp','w',encoding='utf-8') as f: json.dump(meta,f,ensure_ascii=False)
    os.replace(APK_META_PATH+'.tmp', APK_META_PATH)
    return web.json_response({'ok':True,**meta})

async def api_iptv_state(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    raw = await get_setting(f'iptv_state:{uid}', '{}')
    try:
        data = json.loads(raw or '{}')
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return web.json_response({
        'ok': True,
        'favorites': list(dict.fromkeys(data.get('favorites') or []))[:500],
        'recent': list(dict.fromkeys(data.get('recent') or []))[:30],
        'last_channel': str(data.get('last_channel') or ''),
        'layout': str(data.get('layout') or ''),
        'tv_mode': bool(data.get('tv_mode')),
        'updated_at': int(data.get('updated_at') or 0),
    }, headers={'Cache-Control':'no-store'})


async def api_iptv_state_save(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    body = await request.json()
    favorites = [str(x) for x in (body.get('favorites') or []) if str(x).strip()][:500]
    recent = [str(x) for x in (body.get('recent') or []) if str(x).strip()][:30]
    state = {
        'favorites': list(dict.fromkeys(favorites)),
        'recent': list(dict.fromkeys(recent)),
        'last_channel': str(body.get('last_channel') or '')[:80],
        'layout': 'grid' if body.get('layout') == 'grid' else 'list',
        'tv_mode': bool(body.get('tv_mode')),
        'updated_at': int(time.time()),
    }
    await set_setting(f'iptv_state:{uid}', json.dumps(state, ensure_ascii=False, separators=(',', ':')))
    return web.json_response({'ok':True, **state}, headers={'Cache-Control':'no-store'})


def _edem_prune_sessions(uid: int, ttl: int = 120):
    now = int(time.time())
    sessions = _edem_sessions.setdefault(uid, {})
    dead = [k for k,v in sessions.items() if now - int(v.get('ts') or 0) > ttl]
    for k in dead:
        sessions.pop(k, None)
    return sessions


async def _edem_max_connections(uid: int) -> int:
    raw = await get_setting(f'edem_max_connections:{uid}', '3')
    try:
        return max(1, min(10, int(raw)))
    except Exception:
        return 3


async def _edem_touch_session(uid: int, device_id: str):
    device_id = (device_id or '').strip()[:120]
    if not device_id:
        device_id = 'unknown'
    sessions = _edem_prune_sessions(uid)
    limit = await _edem_max_connections(uid)
    if device_id not in sessions and len(sessions) >= limit:
        return False, limit, len(sessions)
    sessions[device_id] = {'ts': int(time.time())}
    return True, limit, len(sessions)


def _edem_stream_token(uid: int, device_id: str, url: str) -> str:
    import hashlib, hmac
    secret = (os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('FACETALK_BOT_TOKEN') or 'abaj-tv').encode()
    payload = f'{uid}|{device_id}|{url}'.encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _edem_store_stream(uid: int, device_id: str, url: str) -> str:
    token = _edem_stream_token(uid, device_id, url)
    _edem_stream_tokens[token] = {
        'uid': uid,
        'device_id': device_id,
        'url': url,
        'ts': int(time.time()),
    }
    return token


def _rewrite_edem_hls(text: str, base: str, uid: int, device_id: str) -> str:
    from urllib.parse import urljoin
    import re
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append('')
            continue
        if line.startswith('#'):
            def repl(match):
                target = urljoin(base, match.group(1))
                token = _edem_store_stream(uid, device_id, target)
                return 'URI="/api/iptv/edem/proxy?t=' + quote(token, safe='') + '"'
            out.append(re.sub(r'URI="([^"]+)"', repl, raw))
        else:
            target = urljoin(base, line)
            token = _edem_store_stream(uid, device_id, target)
            out.append('/api/iptv/edem/proxy?t=' + quote(token, safe=''))
    return '\n'.join(out) + '\n'


async def api_iptv_edem_proxy(request):
    token = (request.query.get('t') or '').strip()
    entry = _edem_stream_tokens.get(token)
    if not entry:
        raise web.HTTPForbidden(text='Invalid stream token')
    uid = int(entry['uid'])
    sub = await _edem_subscription_state(uid)
    if not sub['active']:
        raise web.HTTPForbidden(text='Subscription expired')
    device_id = str(entry['device_id'])
    ok, limit, active = await _edem_touch_session(uid, device_id)
    if not ok:
        raise web.HTTPTooManyRequests(text=f'Connection limit reached ({active}/{limit})')
    if int(time.time()) - int(entry.get('ts') or 0) > 600:
        _edem_stream_tokens.pop(token, None)
        raise web.HTTPForbidden(text='Expired stream token')
    url = entry['url']
    timeout = aiohttp.ClientTimeout(total=20, connect=6, sock_read=12)
    async with aiohttp.ClientSession(headers={'User-Agent':'AbajTV/1.0'}) as session:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            body = await r.read()
            ctype = (r.headers.get('content-type') or '').lower()
            final_url = str(r.url)
            status = r.status
    if b'#EXTM3U' in body[:4096] or 'mpegurl' in ctype or final_url.lower().split('?')[0].endswith('.m3u8'):
        return web.Response(
            text=_rewrite_edem_hls(body.decode('utf-8','ignore'), final_url, uid, device_id),
            content_type='application/vnd.apple.mpegurl',
            headers={'Cache-Control':'no-store'}
        )
    return web.Response(
        body=body,
        status=status,
        content_type=ctype.split(';')[0] if ctype else 'application/octet-stream',
        headers={'Cache-Control':'private, max-age=20'}
    )


async def _edem_payment_state(uid: int):
    raw = await get_setting(f'edem_payment:{uid}', '{}')
    try:
        data = json.loads(raw or '{}')
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return {
        'status': str(data.get('status') or 'none'),
        'last_paid_at': int(data.get('last_paid_at') or 0),
        'plan_days': int(data.get('plan_days') or 30),
        'last_amount': float(data.get('last_amount') or 0),
    }


async def _edem_subscription_state(uid: int):
    raw = await get_setting(f'edem_expires_at:{uid}', '0')
    try:
        expires_at = max(0, int(raw or 0))
    except Exception:
        expires_at = 0
    now = int(time.time())
    active = expires_at == 0 or expires_at > now
    days_left = None if expires_at == 0 else max(0, (expires_at - now + 86399) // 86400)
    return {
        'active': active,
        'expires_at': expires_at,
        'days_left': days_left,
    }


async def _load_edem_playlist_for_uid(uid: int, force: bool = False):
    sub = await _edem_subscription_state(uid)
    raw = await get_setting(f'edem_playlist:{uid}', '')
    playlist_url = (raw or '').strip()
    if not playlist_url:
        return {'configured': False, 'channels': [], 'playlist_url': '', **sub}
    if not sub['active']:
        return {'configured': True, 'channels': [], 'playlist_url': playlist_url, **sub}
    parsed = urlparse(playlist_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return {'configured': True, 'channels': [], 'playlist_url': '', 'error': 'invalid playlist url'}

    cached = _edem_cache.get(uid) or {}
    now = int(time.time())
    if not force and cached.get('url') == playlist_url and now - int(cached.get('ts') or 0) < 600:
        return {'configured': True, 'channels': cached.get('channels') or [], 'playlist_url': playlist_url, **sub}

    timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=15)
    async with aiohttp.ClientSession(headers={'User-Agent':'AbajTV/1.0'}) as session:
        async with session.get(playlist_url, timeout=timeout, allow_redirects=True) as r:
            if r.status >= 400:
                raise web.HTTPBadGateway(text=f'Edem playlist HTTP {r.status}')
            text = await r.text(errors='ignore')

    rows = iptv._parse_m3u(text, 'ED', playlist_url)
    out = []
    for row in rows[:2500]:
        item = dict(row)
        item['status'] = 'ONLINE'
        item['latency_ms'] = 0
        item['backup_count'] = 0
        item['candidate_count'] = 1
        item['personal'] = True
        item['provider'] = 'Edem'
        out.append(item)
    _edem_cache[uid] = {'url': playlist_url, 'ts': now, 'channels': out}
    return {'configured': True, 'channels': out, 'playlist_url': playlist_url, **sub}


async def api_iptv_edem_status(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    raw = await get_setting(f'edem_playlist:{uid}', '')
    sub = await _edem_subscription_state(uid)
    pay = await _edem_payment_state(uid)
    return web.json_response({
        'ok': True,
        'configured': bool((raw or '').strip()),
        **sub,
        'payment': pay,
    }, headers={'Cache-Control':'no-store'})


async def api_iptv_edem_channels(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    data = await _load_edem_playlist_for_uid(uid, force=request.query.get('refresh') == '1')
    safe = []
    for item in data.get('channels') or []:
        row = dict(item)
        row.pop('url', None)
        row.pop('source', None)
        safe.append(row)
    return web.json_response({
        'ok': True,
        'configured': data.get('configured', False),
        'active': data.get('active', True),
        'expires_at': int(data.get('expires_at') or 0),
        'days_left': data.get('days_left'),
        'channels': safe,
        'count': len(safe),
    }, headers={'Cache-Control':'no-store'})


async def api_iptv_edem_play(request):
    user = await _user_from_request(request)
    if not user:
        raise web.HTTPUnauthorized(text='Unauthorized')
    uid = int(user['id'])
    sub = await _edem_subscription_state(uid)
    if not sub['active']:
        return web.json_response({'ok':False,'error':'subscription_expired','expires_at':sub['expires_at']}, status=403)
    device_id = (request.headers.get('X-Abaj-Device-Id') or '').strip()[:120] or 'unknown'
    ok, limit, active = await _edem_touch_session(uid, device_id)
    if not ok:
        return web.json_response({
            'ok':False,
            'error':'connection_limit',
            'limit':limit,
            'active':active,
        }, status=429)
    cid = (request.query.get('id') or '').strip()
    data = await _load_edem_playlist_for_uid(uid)
    item = next((x for x in (data.get('channels') or []) if x.get('id') == cid), None)
    if not item:
        raise web.HTTPNotFound(text='Channel unavailable')
    url = item.get('url') or ''
    timeout = aiohttp.ClientTimeout(total=18, connect=6, sock_read=10)
    async with aiohttp.ClientSession(headers={'User-Agent':'AbajTV/1.0'}) as session:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            if r.status >= 400:
                raise web.HTTPBadGateway(text=f'Upstream HTTP {r.status}')
            ctype = (r.headers.get('content-type') or '').lower()
            final_url = str(r.url)
            body = await r.read()
    if b'#EXTM3U' in body[:4096] or 'mpegurl' in ctype or final_url.lower().split('?')[0].endswith('.m3u8'):
        return web.Response(
            text=_rewrite_edem_hls(body.decode('utf-8','ignore'), final_url, uid, device_id),
            content_type='application/vnd.apple.mpegurl',
            headers={'Cache-Control':'no-store'}
        )
    raise web.HTTPBadGateway(text='Unsupported Edem stream type')


async def api_admin_iptv_edem_list(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    rows = await list_settings_prefix('edem_playlist:')
    users = []
    for row in rows:
        key = row.get('key') or ''
        try:
            uid = int(key.split(':',1)[1])
        except Exception:
            continue
        playlist = str(row.get('value') or '').strip()
        if not playlist:
            continue
        sessions = _edem_prune_sessions(uid)
        limit = await _edem_max_connections(uid)
        cache = _edem_cache.get(uid) or {}
        sub = await _edem_subscription_state(uid)
        pay = await _edem_payment_state(uid)
        users.append({
            'user_id': uid,
            'configured': True,
            'channel_count': len(cache.get('channels') or []),
            'active_connections': len(sessions),
            'max_connections': limit,
            'last_playlist_refresh': int(cache.get('ts') or 0),
            'active': sub['active'],
            'expires_at': sub['expires_at'],
            'days_left': sub['days_left'],
            'payment_status': pay['status'],
            'last_paid_at': pay['last_paid_at'],
            'plan_days': pay['plan_days'],
            'last_amount': pay['last_amount'],
        })
    users.sort(key=lambda x: x['user_id'])
    return web.json_response({'ok':True,'users':users}, headers={'Cache-Control':'no-store'})


async def api_admin_iptv_edem_limit(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
        limit = max(1, min(10, int(body.get('max_connections'))))
    except Exception:
        return web.json_response({'ok':False,'error':'bad values'}, status=400)
    await set_setting(f'edem_max_connections:{uid}', str(limit))
    return web.json_response({'ok':True,'user_id':uid,'max_connections':limit})


async def api_admin_iptv_edem_payment(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
        plan_days = max(1, min(3650, int(body.get('plan_days') or 30)))
        amount = max(0.0, float(body.get('amount') or 0))
    except Exception:
        return web.json_response({'ok':False,'error':'bad values'}, status=400)
    action = str(body.get('action') or 'paid').strip().lower()
    now = int(time.time())
    if action == 'pending':
        pay = {'status':'pending','last_paid_at':0,'plan_days':plan_days,'last_amount':amount}
        await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
        return web.json_response({'ok':True,'user_id':uid,'payment':pay})
    if action != 'paid':
        return web.json_response({'ok':False,'error':'bad action'}, status=400)

    sub = await _edem_subscription_state(uid)
    base = max(now, int(sub.get('expires_at') or 0))
    expires_at = base + plan_days * 86400
    await set_setting(f'edem_expires_at:{uid}', str(expires_at))
    pay = {'status':'paid','last_paid_at':now,'plan_days':plan_days,'last_amount':amount}
    await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
    sub = await _edem_subscription_state(uid)
    return web.json_response({'ok':True,'user_id':uid,'payment':pay,**sub})


async def api_admin_iptv_edem_subscription(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
    except Exception:
        return web.json_response({'ok':False,'error':'bad user_id'}, status=400)
    expires_at = body.get('expires_at', 0)
    try:
        expires_at = max(0, int(expires_at or 0))
    except Exception:
        return web.json_response({'ok':False,'error':'bad expires_at'}, status=400)
    await set_setting(f'edem_expires_at:{uid}', str(expires_at))
    if expires_at and expires_at <= int(time.time()):
        _edem_sessions.pop(uid, None)
    sub = await _edem_subscription_state(uid)
    return web.json_response({'ok':True,'user_id':uid,**sub})


async def api_admin_iptv_edem_assign(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
    except Exception:
        return web.json_response({'ok':False,'error':'bad user_id'}, status=400)
    playlist_url = str(body.get('playlist_url') or '').strip()
    if playlist_url:
        parsed = urlparse(playlist_url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:
            return web.json_response({'ok':False,'error':'invalid playlist_url'}, status=400)
    await set_setting(f'edem_playlist:{uid}', playlist_url)
    if 'expires_at' in body:
        try:
            expires_at = max(0, int(body.get('expires_at') or 0))
        except Exception:
            return web.json_response({'ok':False,'error':'bad expires_at'}, status=400)
        await set_setting(f'edem_expires_at:{uid}', str(expires_at))
    elif not playlist_url:
        await set_setting(f'edem_expires_at:{uid}', '0')
    _edem_cache.pop(uid, None)
    if not playlist_url:
        _edem_sessions.pop(uid, None)
    sub = await _edem_subscription_state(uid)
    return web.json_response({'ok':True,'user_id':uid,'configured':bool(playlist_url),**sub})


async def api_app_auth_start(request):
    me = await request.app['bot'].get_me()
    username = (me.username or '').lstrip('@')
    if not username: raise web.HTTPServiceUnavailable(text='Telegram bot username unavailable')
    raise web.HTTPFound(f'https://t.me/{quote(username)}?start=app_login')

async def api_app_auth_complete(request):
    init_data = (request.query.get('init_data') or '').strip()
    if not validate_init_data(init_data, max_age=7*86400): raise web.HTTPForbidden(text='Invalid or expired Telegram login')
    raise web.HTTPFound('facetalk://auth?' + urlencode({'init_data':init_data}))

async def start_webapp(bot):
    app = web.Application(client_max_size=100*1024*1024, middlewares=[api_error_middleware]); app['bot']=bot
    app.router.add_get('/', index)
    iptv.install(app)
    app.router.add_get('/api/app-release', api_app_release); app.router.add_get('/api/app-download', api_app_download); app.router.add_get(PUBLIC_APK_PATH, api_app_download); app.router.add_get('/downloads/FaceTalkAI-latest.apk', api_app_download); app.router.add_post('/api/app-upload', api_app_upload)
    app.router.add_get('/api/admin/app-release', api_app_release); app.router.add_get('/api/admin/app-download', api_app_download); app.router.add_post('/api/admin/app-upload', api_app_upload)
    app.router.add_get('/api/app-auth/telegram-start', api_app_auth_start); app.router.add_get('/api/app-auth/complete', api_app_auth_complete)
    app.router.add_get('/api/iptv/state', api_iptv_state); app.router.add_post('/api/iptv/state', api_iptv_state_save)
    app.router.add_get('/api/iptv/edem/status', api_iptv_edem_status); app.router.add_get('/api/iptv/edem/channels', api_iptv_edem_channels); app.router.add_get('/api/iptv/edem/play', api_iptv_edem_play); app.router.add_get('/api/iptv/edem/proxy', api_iptv_edem_proxy)
    app.router.add_get('/api/admin/iptv/edem', api_admin_iptv_edem_list); app.router.add_post('/api/admin/iptv/edem/assign', api_admin_iptv_edem_assign); app.router.add_post('/api/admin/iptv/edem/limit', api_admin_iptv_edem_limit); app.router.add_post('/api/admin/iptv/edem/subscription', api_admin_iptv_edem_subscription); app.router.add_post('/api/admin/iptv/edem/payment', api_admin_iptv_edem_payment)
    app.router.add_get('/api/me', api_me); app.router.add_get('/api/admin/stats', api_admin_stats); app.router.add_get('/api/admin/keys', api_admin_keys); app.router.add_post('/api/admin/keys', api_admin_keys)
    app.router.add_get('/api/admin/gpu-health', api_admin_gpu_health); app.router.add_post('/api/admin/video-limit', api_admin_video_limit)
    app.router.add_get('/api/photo', api_photo); app.router.add_get('/api/profile-photo', api_profile_photo); app.router.add_post('/api/role', api_role); app.router.add_post('/api/mode', api_mode); app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo); app.router.add_post('/api/voice-clone', api_voice_clone); app.router.add_post('/api/voice-clone/delete', api_delete_voice_clone); app.router.add_post('/api/profile/select', api_profile_select); app.router.add_post('/api/profile/rename', api_profile_rename); app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False); app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup(); site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    print('IPTV Player web endpoints active')
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app)); return runner
