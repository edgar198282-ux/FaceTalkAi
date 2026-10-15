import asyncio
import base64
import hashlib
import html
import io
import json
import os
import secrets
import time
from urllib.parse import urlencode, quote, urlparse

import aiohttp
import qrcode
from aiohttp import web
from cryptography.fernet import Fernet, InvalidToken

from .config import TELEGRAM_BOT_TOKEN
from .db import get_setting, set_setting

PROVIDERS = {
    'google': ('Google Диск', 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token'),
    'yandex': ('Яндекс Диск', 'https://oauth.yandex.ru/authorize', 'https://oauth.yandex.ru/token'),
}
_pending = {}
_streams = {}
_locks = {}


def _cipher():
    key = os.getenv('MEDIA_TOKEN_KEY') or TELEGRAM_BOT_TOKEN
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('abaj-media:' + key).encode()).digest()))


def _credentials(provider):
    prefix = 'MEDIA_' + provider.upper()
    return os.getenv(prefix + '_CLIENT_ID', '').strip(), os.getenv(prefix + '_CLIENT_SECRET', '').strip()


def _callback(provider):
    origin = os.getenv('MEDIA_PUBLIC_URL', '').rstrip('/')
    if not origin:
        domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
        origin = 'https://' + domain if domain else ''
    if not origin:
        origin = os.getenv('MINIAPP_URL', '').split('?')[0].rstrip('/')
    parsed = urlparse(origin)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise web.HTTPServiceUnavailable(text='Media public URL is not configured')
    return f'{parsed.scheme}://{parsed.netloc}/api/media/callback/{provider}'


def _prune():
    now = time.time()
    for mapping in (_pending, _streams):
        for key, value in list(mapping.items()):
            if value['expires'] <= now:
                mapping.pop(key, None)


async def _tokens(uid, provider):
    raw = await get_setting(f'media_tokens:{uid}:{provider}', '')
    try:
        return json.loads(_cipher().decrypt(raw.encode()).decode()) if raw else {}
    except (InvalidToken, ValueError):
        return {}


async def _save(uid, provider, data):
    await set_setting(f'media_tokens:{uid}:{provider}', _cipher().encrypt(json.dumps(data).encode()).decode())


async def _json(method, url, **kwargs):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        async with session.request(method, url, **kwargs) as response:
            if response.status >= 400:
                if response.status in (401, 403):
                    raise web.HTTPUnauthorized(text='Подключите облако заново')
                raise web.HTTPBadGateway(text='Облако временно недоступно')
            return await response.json(content_type=None)


async def _access(uid, provider):
    lock = _locks.setdefault((uid, provider), asyncio.Lock())
    async with lock:
        data = await _tokens(uid, provider)
        if not data.get('access_token'):
            raise web.HTTPUnauthorized(text='Подключите облако')
        if data.get('expires', 0) < time.time() + 60:
            if not data.get('refresh_token'):
                raise web.HTTPUnauthorized(text='Подключите облако заново')
            client, secret = _credentials(provider)
            update = await _json('POST', PROVIDERS[provider][2], data={
                'grant_type': 'refresh_token', 'refresh_token': data['refresh_token'],
                'client_id': client, 'client_secret': secret,
            })
            data.update(update)
            data['expires'] = time.time() + int(update.get('expires_in', 3600))
            await _save(uid, provider, data)
        return {'Authorization': ('Bearer ' if provider == 'google' else 'OAuth ') + data['access_token']}


def _capability(uid, provider, file_id, preview=""):
    _prune()
    if len(_streams) >= 5000:
        _streams.pop(next(iter(_streams)))
    key = secrets.token_urlsafe(32)
    _streams[key] = {'uid': uid, 'provider': provider, 'id': file_id, 'preview': preview, 'expires': time.time() + 7200}
    return '/api/media/stream/' + key


def _page(message):
    return web.Response(text='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>ABAJ TV</title><body style="background:#061426;color:#eef8ff;font:20px Arial;text-align:center;padding:15vh 24px"><h1>ABAJ TV · Медиа</h1><p>' + html.escape(message) + '</p></body></html>', content_type='text/html', headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"})


def register(app, authenticate):
    async def uid(request):
        user = await authenticate(request)
        if not user:
            raise web.HTTPUnauthorized(text='Войдите в ABAJ TV')
        return int(user['id'])

    def provider(request):
        name = request.match_info['provider']
        if name not in PROVIDERS:
            raise web.HTTPNotFound()
        return name

    async def status(request):
        user_id = await uid(request)
        _prune()
        accounts = []
        for name, spec in PROVIDERS.items():
            data = await _tokens(user_id, name)
            pending = next((p for p in _pending.values() if p['uid'] == user_id and p['provider'] == name and p.get('tokens')), None)
            accounts.append({'id': name, 'name': spec[0], 'configured': all(_credentials(name)), 'connected': bool(data.get('access_token')), 'account': data.get('account', ''), 'pending': pending.get('account', '') if pending else ''})
        return web.json_response({'providers': accounts}, headers={'Cache-Control': 'no-store'})

    async def connect(request):
        user_id, name = await uid(request), provider(request)
        client, secret = _credentials(name)
        if not client or not secret:
            return web.json_response({'error': 'Подключение этого облака ещё не настроено'}, status=503)
        _prune()
        for key, old in list(_pending.items()):
            if old['uid'] == user_id and old['provider'] == name:
                _pending.pop(key, None)
        if len(_pending) >= 500:
            raise web.HTTPTooManyRequests()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        params = {'client_id': client, 'response_type': 'code', 'redirect_uri': _callback(name), 'state': state}
        if name == 'google':
            params.update(scope='https://www.googleapis.com/auth/drive.readonly', access_type='offline', prompt='consent', code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='), code_challenge_method='S256')
        url = PROVIDERS[name][1] + '?' + urlencode(params)
        _pending[state] = {'uid': user_id, 'provider': name, 'expires': time.time() + 600, 'verifier': verifier, 'url': url}
        return web.json_response({'url': url, 'qr': '/api/media/qr/' + state, 'expires_in': 600}, headers={'Cache-Control': 'no-store'})

    async def qr(request):
        _prune()
        pending = _pending.get(request.match_info['state'])
        if not pending:
            raise web.HTTPNotFound()
        image = qrcode.make(pending['url'])
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return web.Response(body=buffer.getvalue(), content_type='image/png', headers={'Cache-Control': 'no-store'})

    async def callback(request):
        name = provider(request)
        _prune()
        state = request.query.get('state', '')
        pending = _pending.get(state)
        if not pending or pending['provider'] != name or pending.get('used'):
            return _page('Ссылка устарела. Начните подключение заново в ABAJ TV.')
        pending['used'] = True
        if request.query.get('error') or not request.query.get('code'):
            return _page('Вход отменён. Вернитесь в ABAJ TV.')
        client, secret = _credentials(name)
        form = {'grant_type': 'authorization_code', 'client_id': client, 'client_secret': secret, 'code': request.query['code'], 'redirect_uri': _callback(name)}
        if name == 'google':
            form['code_verifier'] = pending['verifier']
        try:
            data = await _json('POST', PROVIDERS[name][2], data=form)
            if not data.get('access_token'):
                raise web.HTTPBadGateway()
            headers = {'Authorization': ('Bearer ' if name == 'google' else 'OAuth ') + data['access_token']}
            if name == 'google':
                info = await _json('GET', 'https://www.googleapis.com/drive/v3/about', params={'fields': 'user(displayName,emailAddress)'}, headers=headers)
                account = info.get('user', {}).get('emailAddress') or info.get('user', {}).get('displayName')
            else:
                info = await _json('GET', 'https://cloud-api.yandex.net/v1/disk', headers=headers)
                account = info.get('user', {}).get('login') or info.get('user', {}).get('display_name')
            pending['account'] = account or PROVIDERS[name][0]
            pending['tokens'] = dict(data, expires=time.time() + int(data.get('expires_in', 31536000)), account=pending['account'])
            return _page('Вход выполнен. Вернитесь в ABAJ TV и подтвердите подключение показанного аккаунта.')
        except (web.HTTPException, aiohttp.ClientError, asyncio.TimeoutError):
            return _page('Не удалось подключить облако. Попробуйте снова в ABAJ TV.')

    async def confirm(request):
        user_id, name = await uid(request), provider(request)
        _prune()
        for key, pending in list(_pending.items()):
            if pending['uid'] == user_id and pending['provider'] == name and pending.get('tokens'):
                await _save(user_id, name, pending['tokens'])
                _pending.pop(key, None)
                return web.json_response({'ok': True})
        raise web.HTTPBadRequest(text='Подтверждение входа не найдено')

    async def disconnect(request):
        user_id, name = await uid(request), provider(request)
        await set_setting(f'media_tokens:{user_id}:{name}', '')
        for mapping in (_pending, _streams):
            for key, item in list(mapping.items()):
                if item['uid'] == user_id and item['provider'] == name:
                    mapping.pop(key, None)
        return web.json_response({'ok': True})

    async def files(request):
        user_id, name = await uid(request), provider(request)
        headers = await _access(user_id, name)
        folder = request.query.get('folder', 'root' if name == 'google' else 'disk:/')[:2048]
        page = request.query.get('page', '')[:1024]
        items = []
        if name == 'google':
            if not all(c.isalnum() or c in '_-' for c in folder):
                raise web.HTTPBadRequest()
            params = {'q': f"'{folder}' in parents and trashed = false and (mimeType = 'application/vnd.google-apps.folder' or mimeType contains 'image/' or mimeType contains 'video/')", 'pageSize': 100, 'fields': 'nextPageToken,files(id,name,mimeType,thumbnailLink)', 'orderBy': 'folder,name_natural'}
            if page:
                params['pageToken'] = page
            data = await _json('GET', 'https://www.googleapis.com/drive/v3/files', params=params, headers=headers)
            rows, next_page = data.get('files', []), data.get('nextPageToken', '')
            for row in rows:
                kind = 'folder' if row['mimeType'] == 'application/vnd.google-apps.folder' else 'video' if row['mimeType'].startswith('video/') else 'photo'
                items.append({'id': row['id'], 'name': row['name'], 'kind': kind, 'url': '' if kind == 'folder' else _capability(user_id, name, row['id'], row.get('thumbnailLink', ''))})
        else:
            try:
                offset = max(0, min(int(page or 0), 1000000))
            except ValueError:
                raise web.HTTPBadRequest()
            data = await _json('GET', 'https://cloud-api.yandex.net/v1/disk/resources', params={'path': folder, 'limit': 100, 'offset': offset, 'sort': 'name', 'preview_size': 'M', 'preview_crop': 'true'}, headers=headers)
            embedded = data.get('_embedded', {})
            rows = embedded.get('items', [])
            next_page = str(offset + len(rows)) if offset + len(rows) < embedded.get('total', 0) else ''
            for row in rows:
                kind = 'folder' if row.get('type') == 'dir' else 'video' if row.get('mime_type', '').startswith('video/') else 'photo' if row.get('mime_type', '').startswith('image/') else ''
                if kind:
                    items.append({'id': row['path'], 'name': row['name'], 'kind': kind, 'url': '' if kind == 'folder' else _capability(user_id, name, row['path'], row.get('preview', ''))})
        for item in items:
            if item['url'] and _streams[item['url'].rsplit('/', 1)[-1]].get('preview'):
                item['thumbnail'] = item['url'] + '?preview=1'
        items.sort(key=lambda item: (item['kind'] != 'folder', item['name'].casefold()))
        return web.json_response({'items': items, 'next': next_page}, headers={'Cache-Control': 'no-store'})

    async def stream(request):
        _prune()
        entry = _streams.get(request.match_info['key'])
        if not entry:
            raise web.HTTPNotFound()
        name = entry['provider']
        headers = await _access(entry['uid'], name)
        preview = entry.get('preview') if request.query.get('preview') == '1' else ''
        if preview:
            host = urlparse(preview).hostname or ''
            if urlparse(preview).scheme != 'https' or not any(host == suffix or host.endswith('.' + suffix) for suffix in ('googleusercontent.com', 'ggpht.com', 'google.com', 'yandex.net', 'yandex.ru')):
                raise web.HTTPBadGateway()
            url = preview
        elif name == 'google':
            url = 'https://www.googleapis.com/drive/v3/files/' + quote(entry['id'], safe='') + '?alt=media'
        else:
            data = await _json('GET', 'https://cloud-api.yandex.net/v1/disk/resources/download', params={'path': entry['id']}, headers=headers)
            url = data.get('href', '')
            host = urlparse(url).hostname or ''
            if urlparse(url).scheme != 'https' or not any(host == suffix or host.endswith('.' + suffix) for suffix in ('yandex.net', 'yandex.ru')):
                raise web.HTTPBadGateway()
        if request.headers.get('Range'):
            headers['Range'] = request.headers['Range']
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=60)) as session:
            async with session.get(url, headers=headers) as upstream:
                if upstream.status not in (200, 206, 416):
                    raise web.HTTPBadGateway(text='Не удалось открыть файл')
                response_headers = {key: upstream.headers[key] for key in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges') if key in upstream.headers}
                content_type = upstream.headers.get('Content-Type', '').lower()
                if upstream.status != 416 and not content_type.startswith(('image/', 'video/', 'application/octet-stream')):
                    raise web.HTTPUnsupportedMediaType(text='Формат файла не поддерживается')
                response_headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "sandbox; default-src 'none'"})
                response = web.StreamResponse(status=upstream.status, headers=response_headers)
                await response.prepare(request)
                try:
                    async for chunk in upstream.content.iter_chunked(128 * 1024):
                        await response.write(chunk)
                except (ConnectionResetError, asyncio.CancelledError):
                    pass
                return response

    app.router.add_get('/api/media/status', status)
    app.router.add_post('/api/media/connect/{provider}', connect)
    app.router.add_get('/api/media/callback/{provider}', callback)
    app.router.add_post('/api/media/confirm/{provider}', confirm)
    app.router.add_post('/api/media/disconnect/{provider}', disconnect)
    app.router.add_get('/api/media/files/{provider}', files)
    app.router.add_get('/api/media/qr/{state}', qr)
    app.router.add_get('/api/media/stream/{key}', stream)
