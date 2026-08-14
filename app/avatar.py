from .config import TMP_DIR
import asyncio
import base64
import os
import tempfile
import aiohttp
from .config import DID_API_KEY, VIDEO_TIMEOUT

API = 'https://api.d-id.com'

def _auth_header():
    key = (DID_API_KEY or '').strip()
    if not key:
        return ''
    if key.lower().startswith('basic '):
        return key
    if ':' in key:
        token = base64.b64encode(key.encode()).decode()
        return f'Basic {token}'
    return f'Basic {key}'

async def _json_or_text(resp):
    try:
        return await resp.json()
    except Exception:
        return {'error': await resp.text()}

async def create_video(photo_bytes: bytes, audio_path: str) -> str | None:
    """Create a talking-head MP4 through D-ID. Returns local path or None.

    Requires DID_API_KEY. Failures are intentionally non-fatal so FaceTalk can
    fall back to voice mode without breaking the conversation.
    """
    if not DID_API_KEY or not photo_bytes or not audio_path:
        return None
    headers = {'Authorization': _auth_header()}
    timeout = aiohttp.ClientTimeout(total=VIDEO_TIMEOUT + 30)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as s:
            form = aiohttp.FormData()
            form.add_field('image', photo_bytes, filename='face.jpg', content_type='image/jpeg')
            async with s.post(f'{API}/images', data=form) as r:
                body = await _json_or_text(r)
                if r.status not in (200, 201):
                    print('D-ID image upload failed:', r.status, body)
                    return None
                image_url = body.get('url') or body.get('source_url')
            if not image_url:
                print('D-ID image response has no URL:', body)
                return None

            form = aiohttp.FormData()
            with open(audio_path, 'rb') as f:
                form.add_field('audio', f, filename='speech.mp3', content_type='audio/mpeg')
                async with s.post(f'{API}/audios', data=form) as r:
                    body = await _json_or_text(r)
                    if r.status not in (200, 201):
                        print('D-ID audio upload failed:', r.status, body)
                        return None
                    audio_url = body.get('url') or body.get('source_url')
            if not audio_url:
                print('D-ID audio response has no URL:', body)
                return None

            payload = {
                'source_url': image_url,
                'script': {'type': 'audio', 'audio_url': audio_url},
                'config': {'fluent': True, 'pad_audio': 0.0}
            }
            async with s.post(f'{API}/talks', json=payload) as r:
                body = await _json_or_text(r)
                if r.status not in (200, 201):
                    print('D-ID talk create failed:', r.status, body)
                    return None
                talk_id = body.get('id')
            if not talk_id:
                return None

            deadline = asyncio.get_running_loop().time() + VIDEO_TIMEOUT
            result_url = None
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(2)
                async with s.get(f'{API}/talks/{talk_id}') as r:
                    body = await _json_or_text(r)
                status = body.get('status')
                if status == 'done':
                    result_url = body.get('result_url')
                    break
                if status in ('error', 'failed', 'rejected'):
                    print('D-ID talk failed:', body)
                    return None
            if not result_url:
                return None
            async with s.get(result_url) as r:
                if r.status != 200:
                    return None
                data = await r.read()
            fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix='.mp4')
            os.close(fd)
            with open(path, 'wb') as f:
                f.write(data)
            return path
    except Exception as e:
        print('D-ID exception:', repr(e))
        return None
