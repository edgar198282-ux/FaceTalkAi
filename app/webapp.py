import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import parse_qsl
from aiohttp import web
from .config import (
    BOT_TOKEN, MINIAPP_URL, ADMIN_ID, DATA_DIR,
    OPENAI_INPUT_USD_PER_1M, OPENAI_OUTPUT_USD_PER_1M,
    OPENAI_TTS_USD_PER_1M_CHARS, DID_USD_PER_VIDEO,
)
from .db import get_user, set_photo, set_role, set_reply_mode, append_history, reset_history, add_usage, video_remaining, admin_stats, set_global_video_limit, get_provider_state, set_provider_state, set_photo_bytes, get_photo_bytes, has_private_photo, set_voice_clone, get_voice_clone, delete_voice_clone
from .roles import ROLES
from .ai import chat, synthesize, transcribe
from .avatar import create_video
from .voiceclone import create_clone, cloned_tts
from .billing import real_openai_costs
from .config import TMP_DIR

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
GEN_DIR = os.path.join(DATA_DIR, 'generated')
os.makedirs(GEN_DIR, exist_ok=True)


def _safe_move(src, dst):
    """Move generated media even when Railway temp/data paths are on different filesystems."""
    import shutil
    try:
        os.replace(src, dst)
    except OSError as e:
        if getattr(e, "errno", None) == 18:  # EXDEV: Invalid cross-device link
            shutil.copy2(src, dst)
            os.remove(src)
        else:
            raise


def validate_init_data(init_data: str, max_age=86400):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        their_hash = data.pop('hash', '')
        auth_date = int(data.get('auth_date', '0'))
        if not their_hash or abs(time.time() - auth_date) > max_age:
            return None
        check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
        secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        ours = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(ours, their_hash):
            return None
        return json.loads(data.get('user', '{}'))
    except Exception:
        return None

def _validate_launch_fallback(uid_raw: str, ts_raw: str, sig: str, max_age=7*86400):
    try:
        uid = int(uid_raw)
        ts = int(ts_raw)
        if not BOT_TOKEN or not sig or abs(time.time() - ts) > max_age:
            return None
        payload = f"{uid}:{ts}"
        expected = hmac.new(BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return {'id': uid}
    except Exception:
        return None

async def _user_from_request(request):
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    user = validate_init_data(init_data)
    # Some Telegram Desktop/WebApp launches can occasionally expose empty initData.
    # The bot therefore adds a signed uid+timestamp to its WebApp button as a safe fallback.
    if not user:
        user = _validate_launch_fallback(
            request.headers.get('X-FaceTalk-Uid', ''),
            request.headers.get('X-FaceTalk-Ts', ''),
            request.headers.get('X-FaceTalk-Sig', ''),
        )
    # DEV_USER_ID is useful for browser testing outside Telegram; leave unset in production.
    if not user and os.getenv('DEV_USER_ID'):
        user = {'id': int(os.getenv('DEV_USER_ID')), 'first_name': 'Dev'}
    return user

@web.middleware
async def api_error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        print('API exception', request.path, repr(e))
        if request.path.startswith('/api/'):
            return web.json_response(
                {'error': f'Серверная ошибка: {type(e).__name__}: {str(e)[:220]}'},
                status=500
            )
        raise

async def index(request):
    return web.FileResponse(os.path.join(WEB_DIR, 'index.html'))

async def api_me(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'error':'unauthorized'}, status=401)
    uid=int(user['id'])
    u=await get_user(uid)
    clone=await get_voice_clone(uid)
    return web.json_response({
        'is_admin': _is_admin_user(user),
        'user': user,
        'role': u['role'],
        'role_title': ROLES.get(u['role'], ROLES['friend'])[0],
        'has_photo': bool(await has_private_photo(uid) or u['photo_file_id']),
        'has_voice_clone': bool(clone and clone.get('voice_id')),
        'voice_clone_name': (clone or {}).get('voice_name'),
        'reply_mode': u['reply_mode'],
        'roles': {k:v[0] for k,v in ROLES.items()},
        'video_ready': bool(os.getenv('DID_API_KEY') or os.getenv('AVATAR_API_KEY')),
        'voice_clone_ready': bool(os.getenv('ELEVENLABS_API_KEY')),
        'video_quota': await video_remaining(uid),
    })

async def api_role(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'}, status=401)
    body = await request.json()
    role = body.get('role','friend')
    if role not in ROLES: return web.json_response({'error':'bad role'}, status=400)
    await set_role(int(user['id']), role)
    return web.json_response({'ok':True, 'role':role, 'title':ROLES[role][0]})

async def api_mode(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'}, status=401)
    body = await request.json()
    mode = 'video' if body.get('mode') == 'video' else 'voice'
    await set_reply_mode(int(user['id']), mode)
    return web.json_response({'ok':True,'mode':mode})

async def api_reset(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'}, status=401)
    await reset_history(int(user['id']))
    return web.json_response({'ok':True})

async def api_upload_photo(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    reader=await request.multipart(); part=await reader.next()
    if not part or part.name!='photo': return web.json_response({'error':'photo required'},status=400)
    data=await part.read(decode=False)
    if not data: return web.json_response({'error':'empty photo'},status=400)
    if len(data)>10*1024*1024: return web.json_response({'error':'too large'},status=413)
    mime=part.headers.get('Content-Type') or 'image/jpeg'
    if not mime.startswith('image/'): return web.json_response({'error':'image required'},status=400)
    await set_photo_bytes(int(user['id']),data,mime)
    return web.json_response({'ok':True,'private':True})

async def _telegram_photo_bytes(bot, file_id):
    import io
    f = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(f.file_path, destination=buf)
    return buf.getvalue()


async def api_photo(request):
    user=await _user_from_request(request)
    if not user: return web.Response(status=401)
    uid=int(user['id'])
    data,mime=await get_photo_bytes(uid)
    if data:
        return web.Response(body=data,content_type=mime or 'image/jpeg',
                            headers={'Cache-Control':'no-store, max-age=0'})
    u=await get_user(uid)
    if u['photo_file_id']:
        try:
            data=await _telegram_photo_bytes(request.app['bot'],u['photo_file_id'])
            return web.Response(body=data,content_type='image/jpeg',
                                headers={'Cache-Control':'no-store, max-age=0'})
        except Exception: pass
    return web.Response(status=404)


def _is_admin_user(user):
    try:
        return bool(ADMIN_ID) and int(user.get("id", 0)) == int(ADMIN_ID)
    except Exception:
        return False

def _estimate_cost(row):
    return (
        row[1] * OPENAI_INPUT_USD_PER_1M / 1_000_000
        + row[2] * OPENAI_OUTPUT_USD_PER_1M / 1_000_000
        + row[3] * OPENAI_TTS_USD_PER_1M_CHARS / 1_000_000
        + row[5] * DID_USD_PER_VIDEO
    )

async def api_admin_stats(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not _is_admin_user(user):
        return web.json_response({"error": "Нет доступа"}, status=403)

    st = await admin_stats()
    state = await get_provider_state("openai")
    real = await real_openai_costs()
    t = st["today"]
    a = st["all"]

    labels = {
        "ok": "Работает",
        "no_credits": "Нет кредитов",
        "bad_key": "Неверный ключ",
        "error": "Ошибка",
        "unknown": "Ещё не проверен",
    }

    return web.json_response({
        "users": st["users"],
        "day": st["day"],
        "video_limit": st["video_limit"],
        "openai": {
            "state": state.get("state", "unknown"),
            "state_label": labels.get(state.get("state", "unknown"), "Неизвестно"),
            "message": state.get("message", ""),
            "real_today_usd": real["today"]["usd"] if real["today"]["ok"] else None,
            "real_month_usd": real["month"]["usd"] if real["month"]["ok"] else None,
            "costs_error": None if real["today"]["ok"] else real["today"]["error"],
            "scope": real["scope"],
            "today_requests": t[0],
            "today_input_tokens": t[1],
            "today_output_tokens": t[2],
            "today_tts_chars": t[3],
            "estimate_today_usd": _estimate_cost(t),
            "estimate_all_usd": _estimate_cost(a),
        },
        "did": {
            "today_attempts": t[4],
            "today_ready": t[5],
            "all_ready": a[5],
            "estimated_today_usd": t[5] * DID_USD_PER_VIDEO,
            "estimated_all_usd": a[5] * DID_USD_PER_VIDEO,
        },
        "all": {
            "requests": a[0],
            "input_tokens": a[1],
            "output_tokens": a[2],
            "tts_chars": a[3],
            "video_attempts": a[4],
            "video_ready": a[5],
        },
    })

async def api_admin_video_limit(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not _is_admin_user(user):
        return web.json_response({"error": "Нет доступа"}, status=403)
    body = await request.json()
    value = max(0, min(100, int(body.get("value", 0))))
    await set_global_video_limit(value)
    return web.json_response({"ok": True, "video_limit": value})

async def api_voice_clone(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    uid=int(user['id']); reader=await request.multipart()
    audio=None; filename='voice.webm'; consent=False
    async for part in reader:
        if part.name=='audio':
            audio=await part.read(decode=False); filename=part.filename or filename
        elif part.name=='consent':
            consent=(await part.text()).strip().lower() in ('1','true','yes','on')
    if not consent:
        return web.json_response({'error':'Подтверди право на использование голоса'},status=400)
    if not audio:
        return web.json_response({'error':'Нет записи голоса'},status=400)
    result=await create_clone(audio,filename=filename,name=f'FaceTalk {uid}')
    await set_voice_clone(uid,result['voice_id'],f'FaceTalk Voice {uid}',True)
    return web.json_response({'ok':True,'requires_verification':bool(result.get('requires_verification'))})

async def api_delete_voice_clone(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    await delete_voice_clone(int(user['id']))
    return web.json_response({'ok':True})

async def api_chat(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    content_type = request.content_type or ''
    if content_type.startswith('multipart/'):
        reader = await request.multipart(); text=''; audio_bytes=None; audio_name='voice.webm'
        async for part in reader:
            if part.name == 'text': text = await part.text()
            elif part.name == 'audio':
                audio_bytes = await part.read(decode=False); audio_name = part.filename or audio_name
        if audio_bytes:
            import tempfile
            suffix = os.path.splitext(audio_name)[1] or '.webm'
            fd, p = tempfile.mkstemp(dir=TMP_DIR, suffix=suffix); os.close(fd)
            with open(p,'wb') as f: f.write(audio_bytes)
            try:
                text, stt_provider = await transcribe(p)
                await set_provider_state(stt_provider,'ok',f'Mini App STT через {stt_provider}')
            finally:
                try: os.remove(p)
                except OSError: pass
    else:
        body = await request.json(); text = (body.get('text') or '').strip()
    if not text: return web.json_response({'error':'empty'}, status=400)

    u = await get_user(uid)
    try:
        reply, usage = await chat(u['role'], u['history'], text)
        provider = usage.get('provider','unknown')
        await set_provider_state(provider,'ok',f'Mini App AI через {provider}')
        await add_usage(uid,text_requests=1,input_tokens=usage.get('input_tokens',0),output_tokens=usage.get('output_tokens',0))
    except Exception as e:
        return web.json_response({'error':'AI: '+str(e)[:220]}, status=502)
    await append_history(uid,'user',text); await append_history(uid,'assistant',reply)
    clone=await get_voice_clone(uid)
    audio_path=None; tts_provider=None
    if clone and clone.get('voice_id'):
        audio_path=await cloned_tts(reply,clone['voice_id'])
        if audio_path: tts_provider='elevenlabs-clone'
    if not audio_path:
        audio_path,tts_provider=await synthesize(reply)
    if audio_path and tts_provider=='openai':
        await add_usage(uid,tts_chars=len(reply))
    out = {'ok':True,'heard':text,'reply':reply,'mode':u['reply_mode']}
    if audio_path:
        try:
            private_photo,private_mime=await get_photo_bytes(uid)
            has_any_photo=bool(private_photo or u['photo_file_id'])
            if u['reply_mode']=='video' and has_any_photo:
                quota=await video_remaining(uid)
                out['video_quota']=quota
                if quota['remaining'] <= 0:
                    out['fallback']='limit'
                else:
                    await add_usage(uid,video_attempts=1)
                    photo_bytes=private_photo
                    if not photo_bytes and u['photo_file_id']:
                        photo_bytes=await _telegram_photo_bytes(request.app['bot'],u['photo_file_id'])
                    video_path=await create_video(photo_bytes,audio_path)
                    if video_path:
                        await add_usage(uid,video_success=1)
                        name = f'{uid}_{uuid.uuid4().hex}.mp4'
                        dest = os.path.join(GEN_DIR,name); _safe_move(video_path,dest)
                        out['video_url'] = f'/generated/{name}'
                    else:
                        out['fallback'] = 'voice'
            if 'video_url' not in out:
                name = f'{uid}_{uuid.uuid4().hex}.mp3'
                dest = os.path.join(GEN_DIR,name); _safe_move(audio_path,dest); audio_path=None
                out['audio_url'] = f'/generated/{name}'
        finally:
            if audio_path:
                try: os.remove(audio_path)
                except OSError: pass
    return web.json_response(out)

async def cleanup_generated(app):
    while True:
        await __import__('asyncio').sleep(1800)
        now=time.time()
        for fn in os.listdir(GEN_DIR):
            p=os.path.join(GEN_DIR,fn)
            try:
                if now-os.path.getmtime(p)>7200: os.remove(p)
            except OSError: pass

async def start_webapp(bot):
    app = web.Application(client_max_size=12*1024*1024, middlewares=[api_error_middleware])
    app['bot']=bot
    app.router.add_get('/', index)
    app.router.add_get('/api/me', api_me)
    app.router.add_get('/api/admin/stats', api_admin_stats)
    app.router.add_post('/api/admin/video-limit', api_admin_video_limit)
    app.router.add_get('/api/photo', api_photo)
    app.router.add_post('/api/role', api_role)
    app.router.add_post('/api/mode', api_mode)
    app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo)
    app.router.add_post('/api/voice-clone', api_voice_clone)
    app.router.add_post('/api/voice-clone/delete', api_delete_voice_clone)
    app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False)
    app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup()
    from .config import PORT
    site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app))
    return runner
