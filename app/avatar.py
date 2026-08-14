from .config import TMP_DIR, VIDEO_TIMEOUT
import asyncio
import base64
import os
import tempfile
import aiohttp
from .runtime_config import runtime_value

DID_API = 'https://api.d-id.com'

def _auth_header(key):
    key = (key or '').strip()
    if not key:
        return ''
    if key.lower().startswith('basic '):
        return key
    if ':' in key:
        return 'Basic ' + base64.b64encode(key.encode()).decode()
    return f'Basic {key}'

async def _json_or_text(resp):
    try:
        return await resp.json()
    except Exception:
        return {'error': await resp.text()}

def _save_mp4(data: bytes) -> str:
    fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix='.mp4')
    os.close(fd)
    with open(path, 'wb') as f:
        f.write(data)
    return path

async def _download_result(session, url: str):
    if not url:
        return None
    async with session.get(url) as r:
        if r.status != 200:
            return None
        return _save_mp4(await r.read())

async def _post_worker(url: str, fields: dict, token: str = ''):
    """Call a FaceTalk GPU worker endpoint.

    Worker contract:
      POST multipart -> either raw video/mp4 OR JSON {result_url|video_url|url}.
    This keeps the Telegram/Railway service independent from the heavy CUDA stack.
    """
    if not url:
        return None
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    timeout = aiohttp.ClientTimeout(total=VIDEO_TIMEOUT + 60)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as s:
            form = aiohttp.FormData()
            opened = []
            try:
                for name, value in fields.items():
                    if isinstance(value, tuple) and len(value) >= 3:
                        filename, path_or_bytes, ctype = value[:3]
                        if isinstance(path_or_bytes, (bytes, bytearray)):
                            form.add_field(name, bytes(path_or_bytes), filename=filename, content_type=ctype)
                        else:
                            f = open(path_or_bytes, 'rb'); opened.append(f)
                            form.add_field(name, f, filename=filename, content_type=ctype)
                    else:
                        form.add_field(name, str(value))
                async with s.post(url, data=form) as r:
                    ctype = (r.headers.get('Content-Type') or '').lower()
                    if r.status not in (200, 201):
                        print('GPU worker failed:', url, r.status, await r.text())
                        return None
                    if 'video/' in ctype or 'application/octet-stream' in ctype:
                        return _save_mp4(await r.read())
                    body = await _json_or_text(r)
                    result_url = body.get('result_url') or body.get('video_url') or body.get('url')
                    return await _download_result(s, result_url)
            finally:
                for f in opened:
                    try: f.close()
                    except Exception: pass
    except Exception as e:
        print('GPU worker exception:', url, repr(e))
        return None

async def _free_gpu_video(photo_bytes: bytes, audio_path: str):
    live_url = (await runtime_value('LIVEPORTRAIT_URL')).rstrip('/')
    muse_url = (await runtime_value('MUSETALK_URL')).rstrip('/')
    token = await runtime_value('GPU_WORKER_TOKEN')
    if not muse_url:
        return None

    # Preferred: one combined FaceTalk worker endpoint. It accepts the original
    # photo + final audio and internally runs LivePortrait then MuseTalk.
    combined = muse_url + '/facetalk'
    out = await _post_worker(combined, {
        'image': ('face.jpg', photo_bytes, 'image/jpeg'),
        'audio': ('speech.mp3', audio_path, 'audio/mpeg'),
        'liveportrait_url': live_url,
    }, token)
    if out:
        return out

    # Compatibility path for two separate workers:
    # LivePortrait /animate: image -> idle portrait MP4
    # MuseTalk /lipsync: source_video + audio -> final MP4
    if live_url:
        idle = await _post_worker(live_url + '/animate', {
            'image': ('face.jpg', photo_bytes, 'image/jpeg'),
        }, token)
        if idle:
            try:
                out = await _post_worker(muse_url + '/lipsync', {
                    'source_video': ('portrait.mp4', idle, 'video/mp4'),
                    'audio': ('speech.mp3', audio_path, 'audio/mpeg'),
                }, token)
                if out:
                    return out
            finally:
                try: os.remove(idle)
                except OSError: pass

    # Some MuseTalk services support static image directly.
    return await _post_worker(muse_url + '/lipsync', {
        'image': ('face.jpg', photo_bytes, 'image/jpeg'),
        'audio': ('speech.mp3', audio_path, 'audio/mpeg'),
    }, token)

async def _did_video(photo_bytes: bytes, audio_path: str):
    key = await runtime_value('DID_API_KEY')
    if not key:
        return None
    headers = {'Authorization': _auth_header(key)}
    timeout = aiohttp.ClientTimeout(total=VIDEO_TIMEOUT + 30)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as s:
            form = aiohttp.FormData(); form.add_field('image', photo_bytes, filename='face.jpg', content_type='image/jpeg')
            async with s.post(f'{DID_API}/images', data=form) as r:
                body = await _json_or_text(r)
                if r.status not in (200, 201): print('D-ID image upload failed:', r.status, body); return None
                image_url = body.get('url') or body.get('source_url')
            if not image_url: return None
            form = aiohttp.FormData()
            with open(audio_path, 'rb') as f:
                form.add_field('audio', f, filename='speech.mp3', content_type='audio/mpeg')
                async with s.post(f'{DID_API}/audios', data=form) as r:
                    body = await _json_or_text(r)
                    if r.status not in (200, 201): print('D-ID audio upload failed:', r.status, body); return None
                    audio_url = body.get('url') or body.get('source_url')
            if not audio_url: return None
            payload = {'source_url': image_url, 'script': {'type': 'audio', 'audio_url': audio_url}, 'config': {'fluent': True, 'pad_audio': 0.0}}
            async with s.post(f'{DID_API}/talks', json=payload) as r:
                body = await _json_or_text(r)
                if r.status not in (200, 201): print('D-ID talk create failed:', r.status, body); return None
                talk_id = body.get('id')
            if not talk_id: return None
            deadline = asyncio.get_running_loop().time() + VIDEO_TIMEOUT
            result_url = None
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(2)
                async with s.get(f'{DID_API}/talks/{talk_id}') as r: body = await _json_or_text(r)
                status = body.get('status')
                if status == 'done': result_url = body.get('result_url'); break
                if status in ('error','failed','rejected'): return None
            return await _download_result(s, result_url)
    except Exception as e:
        print('D-ID exception:', repr(e)); return None

async def create_video(photo_bytes: bytes, audio_path: str) -> str | None:
    if not photo_bytes or not audio_path:
        return None
    engine = (await runtime_value('AVATAR_ENGINE', 'auto') or 'auto').strip().lower()
    # auto/free_gpu: free self-hosted path first. D-ID is only a fallback in auto.
    if engine in ('auto', 'free_gpu', 'liveportrait', 'musetalk'):
        out = await _free_gpu_video(photo_bytes, audio_path)
        if out:
            return out
        if engine != 'auto':
            return None
    if engine in ('auto', 'did'):
        return await _did_video(photo_bytes, audio_path)
    return None
