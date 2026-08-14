import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import parse_qsl
from aiohttp import web
from aiogram.types import BufferedInputFile
from .config import BOT_TOKEN, MINIAPP_URL
from .db import get_user, set_photo, set_role, set_reply_mode, append_history, reset_history
from .roles import ROLES
from .ai import chat, synthesize, transcribe
from .avatar import create_video

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
GEN_DIR = os.path.join(BASE_DIR, 'generated')
os.makedirs(GEN_DIR, exist_ok=True)


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

async def _user_from_request(request):
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    user = validate_init_data(init_data)
    # DEV_USER_ID is useful for browser testing outside Telegram; leave unset in production.
    if not user and os.getenv('DEV_USER_ID'):
        user = {'id': int(os.getenv('DEV_USER_ID')), 'first_name': 'Dev'}
    return user

async def index(request):
    return web.FileResponse(os.path.join(WEB_DIR, 'index.html'))

async def api_me(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'error':'unauthorized'}, status=401)
    u = await get_user(int(user['id']))
    return web.json_response({
        'user': user,
        'role': u['role'],
        'role_title': ROLES.get(u['role'], ROLES['friend'])[0],
        'has_photo': bool(u['photo_file_id']),
        'reply_mode': u['reply_mode'],
        'roles': {k:v[0] for k,v in ROLES.items()},
        'video_ready': bool(os.getenv('DID_API_KEY') or os.getenv('AVATAR_API_KEY')),
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
    user = await _user_from_request(request)
    if not user: return web.json_response({'error':'unauthorized'}, status=401)
    reader = await request.multipart()
    part = await reader.next()
    if not part or part.name != 'photo': return web.json_response({'error':'photo required'}, status=400)
    data = await part.read(decode=False)
    if len(data) > 10*1024*1024: return web.json_response({'error':'too large'}, status=413)
    bot = request.app['bot']
    sent = await bot.send_photo(int(user['id']), BufferedInputFile(data, filename='facetalk.jpg'), caption='✅ Фото FaceTalk обновлено')
    await set_photo(int(user['id']), sent.photo[-1].file_id)
    # Keep the confirmation visible: users know which photo is active.
    return web.json_response({'ok':True})

async def _telegram_photo_bytes(bot, file_id):
    f = await bot.get_file(file_id)
    buf = bytearray()
    class Sink:
        def write(self, b): buf.extend(b)
    await bot.download_file(f.file_path, destination=Sink())
    return bytes(buf)

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
            fd, p = tempfile.mkstemp(suffix=suffix); os.close(fd)
            with open(p,'wb') as f: f.write(audio_bytes)
            try: text = await transcribe(p)
            finally:
                try: os.remove(p)
                except OSError: pass
    else:
        body = await request.json(); text = (body.get('text') or '').strip()
    if not text: return web.json_response({'error':'empty'}, status=400)

    u = await get_user(uid)
    reply = await chat(u['role'], u['history'], text)
    await append_history(uid,'user',text); await append_history(uid,'assistant',reply)
    audio_path = await synthesize(reply)
    out = {'ok':True,'heard':text,'reply':reply,'mode':u['reply_mode']}
    if audio_path:
        try:
            if u['reply_mode']=='video' and u['photo_file_id']:
                photo_bytes = await _telegram_photo_bytes(request.app['bot'], u['photo_file_id'])
                video_path = await create_video(photo_bytes, audio_path)
                if video_path:
                    name = f'{uid}_{uuid.uuid4().hex}.mp4'
                    dest = os.path.join(GEN_DIR,name); os.replace(video_path,dest)
                    out['video_url'] = f'/generated/{name}'
                else:
                    out['fallback'] = 'voice'
            if 'video_url' not in out:
                name = f'{uid}_{uuid.uuid4().hex}.mp3'
                dest = os.path.join(GEN_DIR,name); os.replace(audio_path,dest); audio_path=None
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
    app = web.Application(client_max_size=12*1024*1024)
    app['bot']=bot
    app.router.add_get('/', index)
    app.router.add_get('/api/me', api_me)
    app.router.add_post('/api/role', api_role)
    app.router.add_post('/api/mode', api_mode)
    app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo)
    app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False)
    app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup()
    from .config import PORT
    site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app))
    return runner
