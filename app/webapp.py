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
from .db import get_user, set_photo, set_role, set_reply_mode, append_history, reset_history, add_usage, video_remaining, admin_stats, set_global_video_limit, get_provider_state, set_provider_state, set_photo_bytes, get_photo_bytes, has_private_photo, set_voice_clone, get_voice_clone, delete_voice_clone, list_person_profiles, create_person_profile, rename_person_profile, select_person_profile, get_active_person_profile, set_person_profile_photo, get_person_profile_photo, delete_person_profile, get_setting, set_setting
from .roles import ROLES
from .ai import chat, synthesize, transcribe
from .avatar import create_video
from .voiceclone import create_clone, cloned_tts
from .billing import real_openai_costs
from .config import TMP_DIR
from .runtime_config import runtime_value, mask_secret, RUNTIME_KEYS

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
    # The standalone Abaj TV APK stores the Telegram-signed login locally so the
    # same account can keep favorites synced with the Mini App between launches.
    # Keep the normal Telegram WebApp window short, but allow the signed APK
    # session to live longer on the user's own device.
    ua = request.headers.get('User-Agent', '')
    init_max_age = 30 * 86400 if 'AbajTV-Android/' in ua else 86400
    user = validate_init_data(init_data, max_age=init_max_age)
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
    resp = web.FileResponse(os.path.join(WEB_DIR, 'index.html'))
    resp.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma']='no-cache'
    return resp

async def api_me(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'error':'unauthorized'}, status=401)
    uid=int(user['id'])
    u=await get_user(uid)
    profiles=await list_person_profiles(uid)
    active=await get_active_person_profile(uid)
    clone=await get_voice_clone(uid)
    return web.json_response({
        'is_admin': _is_admin_user(user),
        'user': user,
        'role': u['role'],
        'role_title': ROLES.get(u['role'], ROLES['friend'])[0],
        'profiles': profiles,
        'active_profile': ({'id':active['id'],'name':active['name'],'has_voice':bool(active.get('voice_id')),'has_photo':bool(active.get('photo'))} if active else None),
        'has_photo': bool((active and active.get('photo')) or await has_private_photo(uid) or u['photo_file_id']),
        'has_voice_clone': bool((active and active.get('voice_id')) or (clone and clone.get('voice_id'))),
        'voice_clone_name': (active or {}).get('name') or (clone or {}).get('voice_name'),
        'reply_mode': u['reply_mode'],
        'roles': {k:v[0] for k,v in ROLES.items()},
        'video_ready': bool((await runtime_value('MUSETALK_URL')) or (await runtime_value('DID_API_KEY'))),
        'avatar_engine': (await runtime_value('AVATAR_ENGINE', 'auto') or 'auto'),
        'voice_clone_ready': bool(await runtime_value('ELEVENLABS_API_KEY')),
        'video_quota': await video_remaining(uid),
        'pending_photo': (await get_setting(f'pending_photo:{uid}', '0')) == '1',
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
    reader=await request.multipart(); data=None; mime='image/jpeg'; profile_id=None
    async for part in reader:
        if part.name=='photo':
            data=await part.read(decode=False); mime=part.headers.get('Content-Type') or 'image/jpeg'
        elif part.name=='profile_id':
            try: profile_id=int((await part.text()).strip())
            except Exception: profile_id=None
    if not data: return web.json_response({'error':'photo required'},status=400)
    if len(data)>10*1024*1024: return web.json_response({'error':'too large'},status=413)
    if not mime.startswith('image/'): return web.json_response({'error':'image required'},status=400)
    uid=int(user['id'])
    if profile_id:
        if not await set_person_profile_photo(uid,profile_id,data,mime):
            return web.json_response({'error':'Профиль не найден'},status=404)
        await set_setting(f'pending_photo:{uid}', '0')
        return web.json_response({'ok':True,'private':True,'bound':True,'profile_id':profile_id})
    # Main flow: first choose/upload a photo, then choose which saved voice/person it belongs to.
    # Keep it as a pending photo until a profile is selected.
    await set_photo_bytes(uid,data,mime)
    await set_setting(f'pending_photo:{uid}', '1')
    return web.json_response({'ok':True,'private':True,'pending_voice_selection':True})

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
    active=await get_active_person_profile(uid)
    data,mime=((active.get('photo'),active.get('mime')) if active and active.get('photo') else (None,None))
    if not data:
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


async def api_admin_keys(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'Unauthorized'}, status=401)
    if not _is_admin_user(user): return web.json_response({'error':'Нет доступа'}, status=403)
    if request.method == 'POST':
        body = await request.json()
        saved = []
        for name in RUNTIME_KEYS:
            if name not in body: continue
            value = str(body.get(name) or '').strip()
            if value:
                await set_setting('runtime:' + name, value)
                saved.append(name)
        return web.json_response({'ok': True, 'saved': saved})
    result = {}
    for name in RUNTIME_KEYS:
        value = await runtime_value(name)
        result[name] = {'configured': bool(value), 'masked': mask_secret(value)}
        if name == 'AVATAR_ENGINE': result[name]['value'] = value or 'auto'
    return web.json_response({'ok': True, 'keys': result})


async def api_admin_gpu_health(request):
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'Unauthorized'}, status=401)
    if not _is_admin_user(user): return web.json_response({'error':'Нет доступа'}, status=403)
    import aiohttp
    base = (await runtime_value('MUSETALK_URL')).rstrip('/')
    token = await runtime_value('GPU_WORKER_TOKEN')
    if not base:
        return web.json_response({'ok':False,'error':'MuseTalk URL не добавлен'}, status=400)
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    try:
        timeout=aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
            async with sess.get(base + '/health') as r:
                raw=await r.text()
                try: data=json.loads(raw)
                except Exception: data={'raw': raw[:500]}
                if r.status != 200:
                    return web.json_response({'ok':False,'status':r.status,'error':data}, status=502)
                return web.json_response({'ok':True,'worker':data})
    except Exception as e:
        return web.json_response({'ok':False,'error':str(e)[:300]}, status=502)

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
    audio=None; filename='voice.webm'; consent=False; name='Новый голос'
    async for part in reader:
        if part.name=='audio':
            audio=await part.read(decode=False); filename=part.filename or filename
        elif part.name=='consent':
            consent=(await part.text()).strip().lower() in ('1','true','yes','on')
        elif part.name=='name':
            name=(await part.text()).strip()[:60] or 'Новый голос'
    if not consent:
        return web.json_response({'error':'Подтверди право на использование голоса'},status=400)
    if not audio:
        return web.json_response({'error':'Нет записи голоса'},status=400)
    result=await create_clone(audio,filename=filename,name=name)
    pid=await create_person_profile(uid,name,result['voice_id'],True)
    if (await get_setting(f'pending_photo:{uid}', '0')) == '1':
        pdata, pmime = await get_photo_bytes(uid)
        if pdata:
            await set_person_profile_photo(uid,pid,pdata,pmime or 'image/jpeg')
        await set_setting(f'pending_photo:{uid}', '0')
    return web.json_response({'ok':True,'profile_id':pid,'requires_verification':bool(result.get('requires_verification'))})

async def api_delete_voice_clone(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    uid=int(user['id'])
    try: body=await request.json()
    except Exception: body={}
    pid=body.get('id')
    if pid:
        if not await delete_person_profile(uid,int(pid)):
            return web.json_response({'error':'Профиль не найден'},status=404)
    else:
        active=await get_active_person_profile(uid)
        if active: await delete_person_profile(uid,active['id'])
        else: await delete_voice_clone(uid)
    return web.json_response({'ok':True})

async def api_profile_select(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    body=await request.json(); pid=int(body.get('id',0) or 0); uid=int(user['id'])
    if not await select_person_profile(uid,pid): return web.json_response({'error':'Профиль не найден'},status=404)
    photo_bound=False
    if (await get_setting(f'pending_photo:{uid}', '0')) == '1':
        pdata, pmime = await get_photo_bytes(uid)
        if pdata:
            photo_bound=bool(await set_person_profile_photo(uid,pid,pdata,pmime or 'image/jpeg'))
        await set_setting(f'pending_photo:{uid}', '0')
    return web.json_response({'ok':True,'photo_bound':photo_bound})

async def api_profile_rename(request):
    user=await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'},status=401)
    body=await request.json(); pid=int(body.get('id',0) or 0)
    if not await rename_person_profile(int(user['id']),pid,body.get('name','')): return web.json_response({'error':'Введите имя'},status=400)
    return web.json_response({'ok':True})

async def api_profile_photo(request):
    user=await _user_from_request(request)
    if not user: return web.Response(status=401)
    try: pid=int(request.query.get('id','0'))
    except Exception: pid=0
    data,mime=await get_person_profile_photo(int(user['id']),pid)
    if not data: return web.Response(status=404)
    return web.Response(body=data,content_type=mime or 'image/jpeg',headers={'Cache-Control':'no-store, max-age=0'})

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
    active_profile=await get_active_person_profile(uid)
    clone=await get_voice_clone(uid)
    audio_path=None; tts_provider=None
    voice_id=(active_profile or {}).get('voice_id') or ((clone or {}).get('voice_id'))
    if voice_id:
        audio_path=await cloned_tts(reply,voice_id)
        if audio_path: tts_provider='elevenlabs-clone'
    if not audio_path:
        audio_path,tts_provider=await synthesize(reply)
    if audio_path and tts_provider=='openai':
        await add_usage(uid,tts_chars=len(reply))
    out = {'ok':True,'heard':text,'reply':reply,'mode':u['reply_mode']}
    if audio_path:
        try:
            private_photo=(active_profile or {}).get('photo')
            private_mime=(active_profile or {}).get('mime')
            if not private_photo:
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
    app.router.add_get('/api/admin/keys', api_admin_keys)
    app.router.add_post('/api/admin/keys', api_admin_keys)
    app.router.add_get('/api/admin/gpu-health', api_admin_gpu_health)
    app.router.add_post('/api/admin/video-limit', api_admin_video_limit)
    app.router.add_get('/api/photo', api_photo)
    app.router.add_get('/api/profile-photo', api_profile_photo)
    app.router.add_post('/api/role', api_role)
    app.router.add_post('/api/mode', api_mode)
    app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo)
    app.router.add_post('/api/voice-clone', api_voice_clone)
    app.router.add_post('/api/voice-clone/delete', api_delete_voice_clone)
    app.router.add_post('/api/profile/select', api_profile_select)
    app.router.add_post('/api/profile/rename', api_profile_rename)
    app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False)
    app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup()
    from .config import PORT
    site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app))
    return runner
