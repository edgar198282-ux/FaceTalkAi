import json
import os
import time
from urllib.parse import quote, urlencode

from aiohttp import web

from .config import DATA_DIR, PORT
from . import iptv
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
    app.router.add_get('/api/me', api_me); app.router.add_get('/api/admin/stats', api_admin_stats); app.router.add_get('/api/admin/keys', api_admin_keys); app.router.add_post('/api/admin/keys', api_admin_keys)
    app.router.add_get('/api/admin/gpu-health', api_admin_gpu_health); app.router.add_post('/api/admin/video-limit', api_admin_video_limit)
    app.router.add_get('/api/photo', api_photo); app.router.add_get('/api/profile-photo', api_profile_photo); app.router.add_post('/api/role', api_role); app.router.add_post('/api/mode', api_mode); app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo); app.router.add_post('/api/voice-clone', api_voice_clone); app.router.add_post('/api/voice-clone/delete', api_delete_voice_clone); app.router.add_post('/api/profile/select', api_profile_select); app.router.add_post('/api/profile/rename', api_profile_rename); app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False); app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup(); site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    print('IPTV Player web endpoints active')
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app)); return runner
