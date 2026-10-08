import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import html
import time
from urllib.parse import quote, urlencode, urlparse, parse_qs

import aiohttp
from aiohttp import web
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .config import DATA_DIR, PORT, ADMIN_ID, TELEGRAM_BOT_TOKEN
from . import iptv
from . import ai as ai_service
from .db import get_setting, set_setting, list_settings_prefix, list_user_ids
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
APK_PATH = os.path.join(APK_DIR, 'AbajTV-latest.apk')
APK_META_PATH = os.path.join(APK_DIR, 'release.json')
APK_BETA_PATH = os.path.join(APK_DIR, 'AbajTV-beta.apk')
APK_BETA_META_PATH = os.path.join(APK_DIR, 'release-beta.json')
APK_HISTORY_DIR = os.path.join(APK_DIR, 'history')
MIN_APK_SIZE = 300_000
PUBLIC_APK_PATH = '/downloads/AbajTV-latest.apk'
PUBLIC_APK_BETA_PATH = '/downloads/AbajTV-beta.apk'
os.makedirs(APK_DIR, exist_ok=True)
os.makedirs(APK_HISTORY_DIR, exist_ok=True)

_edem_cache = {}
_edem_sessions = {}
_edem_stream_tokens = {}
_kinopub_stream_tokens = {}

KINOPUB_API_BASE = (os.getenv('KINOPUB_API_BASE_URL') or 'https://api.service-kp.com').rstrip('/')
KINOPUB_CLIENT_ID = (os.getenv('KINOPUB_API_CLIENT_ID') or 'xbmc').strip()
KINOPUB_CLIENT_SECRET = (os.getenv('KINOPUB_API_CLIENT_SECRET') or 'cgg3gtifu46urtfp2zp1nqtba0k2ezxh').strip()

async def _kinopub_api(method, path, params=None, json_body=None, form_body=None, timeout=20):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.request(
            method,
            KINOPUB_API_BASE + path,
            params=params,
            json=json_body,
            data=form_body,
        ) as resp:
            raw = await resp.text(errors='ignore')
            try:
                data = json.loads(raw or '{}')
            except Exception:
                data = {}
            return resp.status, data

async def _kinopub_tokens(uid):
    raw = await get_setting(f'kinopub_tokens:{uid}', '')
    try:
        data = json.loads(raw or '{}')
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

async def _kinopub_save_tokens(uid, data):
    access = str(data.get('access_token') or '').strip()
    if not access:
        return {}
    current = await _kinopub_tokens(uid)
    refresh = str(data.get('refresh_token') or current.get('refresh_token') or '').strip()
    try:
        expires_in = int(data.get('expires_in') or 0)
    except Exception:
        expires_in = 0
    payload = {
        'access_token': access,
        'refresh_token': refresh,
        'expires_at': int(time.time()) + expires_in if expires_in > 0 else 0,
        'updated_at': int(time.time()),
    }
    await set_setting(f'kinopub_tokens:{uid}', json.dumps(payload, separators=(',', ':')))
    if ADMIN_ID and int(uid) == int(ADMIN_ID):
        await set_setting('kinopub_owner_uid', str(int(uid)))
    return payload

async def _kinopub_access_token(uid):
    async def resolve(owner, tokens):
        access = str(tokens.get('access_token') or '').strip()
        refresh = str(tokens.get('refresh_token') or '').strip()
        expires_at = int(tokens.get('expires_at') or 0)

        if access and (not expires_at or expires_at > int(time.time()) + 90):
            return access

        if refresh:
            status, data = await _kinopub_api('POST', '/oauth2/token', params={
                'grant_type':'refresh_token',
                'client_id':KINOPUB_CLIENT_ID,
                'client_secret':KINOPUB_CLIENT_SECRET,
                'refresh_token':refresh,
            })
            if status < 400 and not data.get('error'):
                fresh = await _kinopub_save_tokens(owner, data)
                return str(fresh.get('access_token') or '')
        return ''

    tokens = await _kinopub_tokens(uid)
    token = await resolve(uid, tokens)
    if token:
        return token

    owner_uid = 0
    try:
        owner_uid = int(str(await get_setting('kinopub_owner_uid', '') or '').strip() or 0)
    except Exception:
        owner_uid = 0
    if not owner_uid and ADMIN_ID:
        owner_uid = int(ADMIN_ID)

    if owner_uid and int(uid) != owner_uid:
        owner_tokens = await _kinopub_tokens(owner_uid)
        token = await resolve(owner_uid, owner_tokens)
        if token:
            return token

    # Never erase stored refresh/access tokens on a transient refresh failure.
    # This lets the next request retry instead of making the whole cinema catalog disappear.
    return ''

def _kinopub_total_from_data(data):
    if isinstance(data, dict):
        for key in ('total','total_items','totalItems','count','items_count'):
            value = data.get(key)
            try:
                if value is not None:
                    return max(0, int(value))
            except Exception:
                pass
        for key in ('pagination','pager','meta','data'):
            value = data.get(key)
            if isinstance(value, dict):
                found = _kinopub_total_from_data(value)
                if found is not None:
                    return found
    return None

def _kinopub_extract_items(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ('items','results','data'):
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict) and isinstance(value.get('items'), list):
            return [x for x in value.get('items') if isinstance(x, dict)]
    return []

def _kinopub_poster(item):
    value = item.get('poster')
    if isinstance(value, str) and value.strip():
        return value.strip()
    for key in ('posters','images'):
        value = item.get(key)
        if isinstance(value, dict):
            for name in ('big','poster','full','wide'):
                url = value.get(name)
                if isinstance(url, str) and url.strip():
                    return url.strip()
    return ''

def _kinopub_backdrop(item):
    for key in ('backdrop','background','fanart','poster_wide','wide_poster'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ('posters','images','backgrounds','backdrops'):
        value = item.get(key)
        if isinstance(value, dict):
            for name in ('wide','backdrop','background','fanart','full','big'):
                url = value.get(name)
                if isinstance(url, str) and url.strip():
                    return url.strip()
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, str) and row.strip():
                    return row.strip()
                if isinstance(row, dict):
                    for name in ('url','src','wide','backdrop','full','big'):
                        url = row.get(name)
                        if isinstance(url, str) and url.strip():
                            return url.strip()
    return ''

def _kinopub_backdrops(item, limit=4):
    rows = []
    seen = set()

    def add(value):
        if isinstance(value, str):
            url = value.strip()
            if url.startswith(('http://','https://')) and url not in seen:
                seen.add(url)
                rows.append(url)

    add(_kinopub_backdrop(item))
    for key in ('backdrop','background','fanart','poster_wide','wide_poster'):
        add(item.get(key))
    for key in ('backgrounds','backdrops','screenshots','stills','gallery','photos','images','posters'):
        value = item.get(key)
        if isinstance(value, dict):
            for name in ('wide','backdrop','background','fanart','full','big','large','url','src','original'):
                add(value.get(name))
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, str):
                    add(row)
                elif isinstance(row, dict):
                    for name in ('wide','backdrop','background','fanart','full','big','large','url','src','original'):
                        add(row.get(name))
                if len(rows) >= limit:
                    break
        if len(rows) >= limit:
            break
    return rows[:max(1, int(limit or 4))]


def _kinopub_kind(item):
    raw_type = str(item.get('type') or '').strip().lower()
    raw_subtype = str(item.get('subtype') or '').strip().lower()
    raw = (raw_type + ' ' + raw_subtype).strip()
    return 'series' if any(x in raw for x in ('serial','series')) else 'movies'

def _kinopub_content_group(item):
    raw_type = str(item.get('type') or '').strip().lower()
    raw_subtype = str(item.get('subtype') or '').strip().lower()
    genres = item.get('genres') or item.get('genre') or ''
    if isinstance(genres, list):
        genre_text = ' '.join(
            str(x.get('title') or x.get('name') or '') if isinstance(x, dict) else str(x or '')
            for x in genres
        ).lower()
    else:
        genre_text = str(genres or '').lower()
    text = ' '.join((raw_type, raw_subtype, genre_text))
    if any(x in text for x in ('аниме','anime')):
        return 'anime'
    if any(x in text for x in ('мульт','cartoon','animation','animated')):
        return 'cartoons'
    if raw_type in ('documovie','documentary','docmovie'):
        return 'docmovies'
    if raw_type in ('docuserial','documentaryseries','docseries'):
        return 'docseries'
    if raw_type == 'tvshow':
        return 'tvshows'
    if raw_type == 'concert':
        return 'concerts'
    return 'series' if _kinopub_kind(item) == 'series' else 'movies'

def _kinopub_actor_image(actor):
    """Extract only portraits supplied by KinoPub, including nested URL variants."""
    if not isinstance(actor, dict):
        return ''
    def image_url(value, depth=0):
        if depth > 4:
            return ''
        if isinstance(value, str):
            url = value.strip()
            if url.startswith(('https://', 'http://')):
                return url
            if url.startswith('//'):
                return 'https:' + url
            return ''
        if isinstance(value, dict):
            for key in ('original','full','large','big','medium','small',
                        'url','src','imageUrl','image_url','path','href','link',
                        'photo','image','poster','avatar','portrait','pictures',
                        'photos','images','file'):
                candidate = image_url(value.get(key), depth + 1)
                if candidate:
                    return candidate
        if isinstance(value, list):
            for entry in value:
                candidate = image_url(entry, depth + 1)
                if candidate:
                    return candidate
        return ''
    for key in ('photo','image','poster','avatar','portrait','picture','thumbnail',
                'photos','images','posters','pictures','portrait_url','photo_url',
                'image_url','avatar_url','photoUrl','imageUrl','profile'):
        candidate = image_url(actor.get(key))
        if candidate:
            return candidate
    return ''

def _kinopub_normalize(item):
    title = str(item.get('title') or item.get('name') or '').strip()
    if not title:
        return None
    countries = item.get('countries') or item.get('country') or ''
    if isinstance(countries, list):
        countries = ', '.join(str(x.get('title') if isinstance(x,dict) else x) for x in countries if x)
    genres = item.get('genres') or item.get('genre') or ''
    if isinstance(genres, list):
        genres = ', '.join(str(x.get('title') if isinstance(x,dict) else x) for x in genres if x)
    directors = item.get('directors') or item.get('director') or ''
    if isinstance(directors, list):
        directors = ', '.join(str(x.get('name') if isinstance(x,dict) else x) for x in directors if x)
    actors_raw = item.get('actors') or item.get('cast') or item.get('actor') or []
    actor_cards = []
    if isinstance(actors_raw, list):
        for actor in actors_raw[:24]:
            if isinstance(actor, dict):
                name = str(actor.get('name') or actor.get('title') or actor.get('full_name') or actor.get('original_name') or actor.get('name_en') or actor.get('english_name') or '').strip()
                search_name = str(actor.get('original_name') or actor.get('name_en') or actor.get('english_name') or actor.get('name') or actor.get('title') or actor.get('full_name') or '').strip()
                image = _kinopub_actor_image(actor)
                if name:
                    actor_cards.append({'id':str(actor.get('id') or actor.get('person_id') or actor.get('actor_id') or ''),'name':name,'search_name':search_name,'image':image})
            elif str(actor or '').strip():
                actor_cards.append({'id':'','name':str(actor).strip(),'image':''})
        actors = ', '.join(x['name'] for x in actor_cards)
    else:
        actors = str(actors_raw or '')
        if actors.strip():
            actor_cards = [{'id':'','name':name.strip(),'search_name':name.strip(),'image':''}
                           for name in re.split(r'[,;]+', actors) if name.strip()][:24]
    translation = item.get('translation') or item.get('translations') or item.get('voice') or ''
    if isinstance(translation, list):
        translation = ', '.join(str(x.get('title') if isinstance(x,dict) else x) for x in translation if x)
    return {
        'id': str(item.get('id') or ''),
        'title': title,
        'original_title': str(item.get('original_title') or ''),
        'year': item.get('year') or '',
        'poster': _kinopub_poster(item),
        'backdrop': _kinopub_backdrop(item),
        'backdrops': _kinopub_backdrops(item, 4),
        'description': str(item.get('plot') or item.get('description') or ''),
        'rating': item.get('imdb_rating') or item.get('rating') or '',
        'kp': item.get('kinopoisk_rating') or item.get('kp_rating') or '',
        'imdb_id': str(item.get('imdb') or item.get('imdb_id') or '').strip(),
        'kp_id': str(item.get('kinopoisk') or item.get('kinopoisk_id') or item.get('kp_id') or '').strip(),
        'kind': _kinopub_kind(item),
        'group': _kinopub_content_group(item),
        'raw_type': str(item.get('type') or ''),
        'raw_subtype': str(item.get('subtype') or ''),
        'country': str(countries or ''),
        'genre': str(genres or ''),
        'director': str(directors or ''),
        'actors': str(actors or ''),
        'actor_cards': actor_cards,
        'translation': str(translation or ''),
        'quality': str(item.get('quality') or item.get('video_quality') or ''),
        'audio': str(item.get('audio') or item.get('audio_codec') or ''),
        'subtitles': item.get('subtitles') or '',
        'trailer': _kinopub_trailer_url(item),
        'source': 'KINOPUB',
    }

async def _cinema_access_allowed(uid: int) -> bool:
    return bool(int(uid))

async def _cinema_playback_allowed(uid: int) -> bool:
    if ADMIN_ID and int(uid) == int(ADMIN_ID):
        return True
    sub = await _edem_subscription_state(int(uid))
    return bool(sub.get('active'))

async def api_cinema_source_state(request):
    user = await _user_from_request(request)
    uid = int(user['id']) if user else 0
    playback_allowed = await _cinema_playback_allowed(uid) if uid else False
    default_source = str(os.getenv('CINEMA_GLOBAL_SOURCE_DEFAULT') or 'kinopub').strip().lower()
    source = str(await get_setting('cinema_global_source', default_source) or default_source).strip().lower()
    if source == 'none':
        source = 'kinopub'
    if source not in ('none','lazy','kinopub'):
        source = 'none'
    return web.json_response({
        'ok':True,
        'source':source,
        'cinema_enabled':True,
        'playback_allowed':bool(playback_allowed),
    }, headers={'Cache-Control':'no-store, max-age=0'})

async def api_admin_cinema_source_state(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    if not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    source = str(body.get('source') or 'none').strip().lower()
    if source not in ('none','lazy','kinopub'):
        return web.json_response({'ok':False,'error':'bad_source'}, status=400)
    await set_setting('cinema_global_source', source)
    return web.json_response({'ok':True,'source':source}, headers={'Cache-Control':'no-store, max-age=0'})

async def _kinopub_validate_saved_connection(uid):
    uid = int(uid)
    token_owner = uid
    tokens = await _kinopub_tokens(uid)

    if not (tokens.get('access_token') or tokens.get('refresh_token')):
        owner_uid = 0
        try:
            owner_uid = int(str(await get_setting('kinopub_owner_uid', '') or '').strip() or 0)
        except Exception:
            owner_uid = 0
        if not owner_uid and ADMIN_ID:
            owner_uid = int(ADMIN_ID)
        if owner_uid and uid != owner_uid:
            owner_tokens = await _kinopub_tokens(owner_uid)
            if owner_tokens.get('access_token') or owner_tokens.get('refresh_token'):
                tokens = owner_tokens
                token_owner = owner_uid

    if not (tokens.get('access_token') or tokens.get('refresh_token')):
        return False, token_owner, False

    access = await _kinopub_access_token(uid)
    if not access:
        return False, token_owner, False

    status, data = await _kinopub_api('GET','/v1/items',params={
        'access_token':access,
        'page':1,
        'perpage':1,
    })
    error = str(data.get('error') or '').lower() if isinstance(data,dict) else ''
    invalid = status in (401,403) or error in (
        'invalid_token','invalid_grant','unauthorized','access_denied'
    )
    if invalid:
        await set_setting(f'kinopub_tokens:{token_owner}', '')
        return False, token_owner, True
    if status >= 400:
        # Do not break an existing connection on a temporary KinoPub outage.
        return True, token_owner, False
    return True, token_owner, False

async def api_kinopub_status(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    if ADMIN_ID and uid == int(ADMIN_ID):
        await set_setting('kinopub_owner_uid', str(uid))

    authenticated, token_owner, revoked = await _kinopub_validate_saved_connection(uid)
    raw = await get_setting(f'kinopub_auth:{uid}', '')
    auth = {}
    try:
        auth = json.loads(raw or '{}')
    except Exception:
        pass
    pending = bool(auth.get('code')) and int(auth.get('expires_at') or 0) > int(time.time())
    subscription_days = None
    subscription_active = None
    if ADMIN_ID and uid == int(ADMIN_ID) and authenticated:
        try:
            token = await _kinopub_access_token(uid)
            if token:
                status, profile = await _kinopub_api('GET', '/v1/user', params={'access_token': token})
                if status < 400 and isinstance(profile, dict):
                    kp_user = profile.get('user') if isinstance(profile.get('user'), dict) else {}
                    sub = kp_user.get('subscription') if isinstance(kp_user.get('subscription'), dict) else {}
                    if sub:
                        subscription_active = bool(sub.get('active'))
                        try:
                            if sub.get('days') is not None:
                                subscription_days = max(0.0, float(sub.get('days')))
                        except Exception:
                            subscription_days = None
                        if subscription_days is None:
                            try:
                                end_time = float(sub.get('end_time') or 0)
                                if end_time > 0:
                                    subscription_days = max(0.0, (end_time - time.time()) / 86400.0)
                            except Exception:
                                pass
        except Exception:
            pass
    return web.json_response({
        'ok':True,
        'authenticated':bool(authenticated),
        'pending':pending,
        'revoked':bool(revoked),
        'owner':bool(ADMIN_ID and token_owner == int(ADMIN_ID)),
        'user_code':str(auth.get('user_code') or ''),
        'verification_uri':str(auth.get('verification_uri') or 'https://kino.pub/device'),
        'subscription_days':subscription_days,
        'subscription_active':subscription_active,
    }, headers={'Cache-Control':'no-store'})

async def api_kinopub_auth_start(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if ADMIN_ID and uid == int(ADMIN_ID):
        await set_setting('kinopub_owner_uid', str(uid))
        await set_setting(f'kinopub_auth:{uid}', '')
    status, data = await _kinopub_api('POST', '/oauth2/device', params={
        'grant_type':'device_code',
        'client_id':KINOPUB_CLIENT_ID,
        'client_secret':KINOPUB_CLIENT_SECRET,
    })
    code = str(data.get('code') or data.get('device_code') or '').strip()
    user_code = str(data.get('user_code') or '').strip()
    if status >= 400 or not code or not user_code:
        return web.json_response({'ok':False,'error':str(data.get('error_description') or data.get('error') or 'kinopub_auth_start_failed')}, status=502)
    try:
        expires_in = int(data.get('expires_in') or 600)
        interval = max(2, int(data.get('interval') or 5))
    except Exception:
        expires_in, interval = 600, 5
    auth = {
        'code':code,
        'user_code':user_code,
        'verification_uri':str(data.get('verification_uri') or data.get('verification_url') or 'https://kino.pub/device'),
        'interval':interval,
        'expires_at':int(time.time()) + max(60, expires_in),
    }
    await set_setting(f'kinopub_auth:{uid}', json.dumps(auth, separators=(',', ':')))
    return web.json_response({
        'ok':True,
        'user_code':user_code,
        'verification_uri':auth['verification_uri'],
        'interval':interval,
        'expires_at':auth['expires_at'],
    }, headers={'Cache-Control':'no-store'})

async def api_kinopub_auth_poll(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    raw = await get_setting(f'kinopub_auth:{uid}', '')
    try:
        auth = json.loads(raw or '{}')
    except Exception:
        auth = {}
    code = str(auth.get('code') or '')
    if not code:
        return web.json_response({'ok':False,'error':'no_pending_auth'}, status=400)
    if int(auth.get('expires_at') or 0) <= int(time.time()):
        return web.json_response({'ok':True,'authenticated':False,'expired':True}, headers={'Cache-Control':'no-store'})
    status, data = await _kinopub_api('POST', '/oauth2/device', params={
        'grant_type':'device_token',
        'client_id':KINOPUB_CLIENT_ID,
        'client_secret':KINOPUB_CLIENT_SECRET,
        'code':code,
    })
    error = str(data.get('error') or '')
    if error in ('authorization_pending','slow_down'):
        return web.json_response({'ok':True,'authenticated':False,'pending':True}, headers={'Cache-Control':'no-store'})
    if error in ('code_expired','authorization_expired'):
        return web.json_response({'ok':True,'authenticated':False,'expired':True}, headers={'Cache-Control':'no-store'})
    if status >= 400 or error:
        return web.json_response({'ok':False,'error':str(data.get('error_description') or error or 'kinopub_auth_failed')}, status=502)
    tokens = await _kinopub_save_tokens(uid, data)
    if not tokens:
        return web.json_response({'ok':False,'error':'kinopub_token_missing'}, status=502)
    await set_setting(f'kinopub_auth:{uid}', '')
    return web.json_response({'ok':True,'authenticated':True}, headers={'Cache-Control':'no-store'})

async def api_kinopub_disconnect(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    await set_setting(f'kinopub_tokens:{uid}', '')
    await set_setting(f'kinopub_auth:{uid}', '')
    return web.json_response({'ok':True}, headers={'Cache-Control':'no-store'})

def _kinopub_walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _kinopub_walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _kinopub_walk(value)

def _kinopub_stream_from_obj(obj):
    if not isinstance(obj, dict):
        return ''
    url = obj.get('url')
    if isinstance(url, str) and url.startswith(('http://','https://')):
        return url
    if isinstance(url, dict):
        for key in ('hls4','hls2','hls','http','dash'):
            value = url.get(key)
            if isinstance(value, str) and value.startswith(('http://','https://')):
                return value
    for key in ('hls4','hls2','hls','http','stream','stream_url','video_url'):
        value = obj.get(key)
        if isinstance(value, str) and value.startswith(('http://','https://')):
            return value
    return ''

def _kinopub_first_media_id(data):
    for obj in _kinopub_walk(data):
        for key in ('media_id','mid'):
            value = obj.get(key)
            if value not in (None,''):
                return str(value)
        if obj.get('files') and obj.get('id') not in (None,''):
            return str(obj.get('id'))
    return ''

def _kinopub_first_file_token(data):
    for obj in _kinopub_walk(data):
        value = obj.get('file')
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''

def _kinopub_stream_token(uid: int, url: str) -> str:
    secret = (TELEGRAM_BOT_TOKEN or os.getenv('FACETALK_BOT_TOKEN') or 'abaj-tv').encode()
    payload = f'kinopub|{int(uid)}|{url}'.encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _kinopub_store_stream(uid: int, url: str) -> str:
    token = _kinopub_stream_token(uid, url)
    _kinopub_stream_tokens[token] = {'uid': int(uid), 'url': str(url), 'ts': int(time.time())}
    return token


def _kinopub_proxy_url(request, uid: int, url: str) -> str:
    external_disabled = str(os.getenv('KINOPUB_PROXY_DISABLED') or '').strip().lower() in {'1','true','yes','on'}
    external_base = str(os.getenv('KINOPUB_PROXY_BASE') or '').strip().rstrip('/')
    external_secret = str(os.getenv('KINOPUB_PROXY_SECRET') or '').strip()
    if not external_disabled and external_base and external_secret:
        payload = json.dumps({
            'u': str(url),
            'e': int(time.time()) + 21600,
            'i': int(uid),
        }, separators=(',', ':')).encode()
        packed = base64.urlsafe_b64encode(payload).decode().rstrip('=')
        sig = hmac.new(external_secret.encode(), packed.encode(), hashlib.sha256).hexdigest()
        return external_base + '/p?t=' + quote(packed + '.' + sig, safe='')
    token = _kinopub_store_stream(uid, url)
    return f'{request.scheme}://{request.host}/api/kinopub/proxy?t={quote(token, safe="")}'


def _kinopub_url_diag(url):
    try:
        p = urlparse(str(url or ''))
        q = parse_qs(p.query or '', keep_blank_values=True)
        now = int(time.time())
        expiry = None
        expiry_key = ''
        for key in ('exp','expires','expire','e','token_exp','hdnts_exp'):
            vals = q.get(key)
            if not vals:
                continue
            raw = str(vals[0] or '').strip()
            try:
                val = int(float(raw))
                if val > 1000000000000:
                    val //= 1000
                if val > 1000000000:
                    expiry = val
                    expiry_key = key
                    break
            except Exception:
                continue
        return {
            'host': str(p.hostname or ''),
            'path': str(p.path or '')[-120:],
            'query_keys': sorted(list(q.keys()))[:24],
            'expiry_key': expiry_key,
            'expiry_in': (expiry-now) if expiry else None,
        }
    except Exception:
        return {'host':'','path':'','query_keys':[],'expiry_key':'','expiry_in':None}

_kinopub_proxy_probe_last = 0.0

async def _kinopub_probe_proxy_ranges(url):
    global _kinopub_proxy_probe_last
    now = time.time()
    if now - _kinopub_proxy_probe_last < 25:
        return
    _kinopub_proxy_probe_last = now
    timeout = aiohttp.ClientTimeout(total=25, connect=5, sock_read=10)
    probes = (
        ('head64k','bytes=0-65535'),
        ('mid64k','bytes=4194304-4259839'),
        ('head4m','bytes=0-4194303'),
        ('mid1m','bytes=67108864-68157439'),
        ('mid2m','bytes=67108864-69206015'),
        ('mid4m','bytes=67108864-71303167'),
    )
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for label, rng in probes:
            started = time.perf_counter()
            total = 0
            first_byte = None
            try:
                async with session.get(url, headers={'Range':rng,'Accept':'*/*'}, allow_redirects=True) as resp:
                    async for chunk in resp.content.iter_chunked(65536):
                        if first_byte is None:
                            first_byte = round((time.perf_counter()-started)*1000)
                        total += len(chunk)
                    elapsed = max(0.001,time.perf_counter()-started)
                    logging.info(
                        'KINOPUB_PROXY_RANGE label=%s status=%s requested=%s content_range=%s content_length=%s accept_ranges=%s bytes=%s first_byte_ms=%s elapsed_ms=%s mbps=%.2f type=%s',
                        label, resp.status, rng,
                        str(resp.headers.get('Content-Range') or ''),
                        str(resp.headers.get('Content-Length') or ''),
                        str(resp.headers.get('Accept-Ranges') or ''),
                        total, first_byte, round(elapsed*1000),
                        (total*8/1000000)/elapsed,
                        str(resp.headers.get('Content-Type') or '')
                    )
            except Exception as exc:
                logging.warning(
                    'KINOPUB_PROXY_RANGE label=%s requested=%s bytes=%s elapsed_ms=%s error=%s',
                    label, rng, total, round((time.perf_counter()-started)*1000),
                    type(exc).__name__+': '+str(exc)[:160]
                )


def _kinopub_direct_stream_response(request, uid, url):
    direct = str(url or '').strip()
    try:
        parsed = urlparse(direct)
    except Exception:
        parsed = None
    if not parsed or parsed.scheme not in ('http','https') or not parsed.netloc:
        return None
    own_host = str(request.host or '').split(':',1)[0].lower()
    stream_host = str(parsed.hostname or '').lower()
    if own_host and stream_host == own_host:
        return None
    diag = _kinopub_url_diag(direct)
    logging.info(
        'KINOPUB_STREAM_URL host=%s expiry_key=%s expiry_in=%s query_keys=%s path=%s',
        diag.get('host'), diag.get('expiry_key'), diag.get('expiry_in'),
        ','.join(diag.get('query_keys') or []), diag.get('path')
    )
    proxied = _kinopub_proxy_url(request, uid, direct)
    return web.json_response({
        'ok': True,
        'url': proxied,
        'provider': 'KINOPUB',
        'direct': False,
        'proxied': True,
    }, headers={'Cache-Control':'no-store'})


def _rewrite_kinopub_hls(text: str, base: str, request, uid: int) -> str:
    from urllib.parse import urljoin
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append('')
            continue
        if line.startswith('#'):
            def repl(match):
                target = urljoin(base, match.group(1))
                return 'URI="' + _kinopub_proxy_url(request, uid, target) + '"'
            out.append(re.sub(r'URI="([^"]+)"', repl, raw))
        else:
            out.append(_kinopub_proxy_url(request, uid, urljoin(base, line)))
    return '\n'.join(out) + '\n'


async def api_kinopub_proxy(request):
    token = str(request.query.get('t') or '').strip()
    entry = _kinopub_stream_tokens.get(token)
    if not entry:
        raise web.HTTPForbidden(text='Invalid KinoPub stream token')

    uid = int(entry.get('uid') or 0)
    if not uid or not await _cinema_playback_allowed(uid):
        raise web.HTTPForbidden(text='Cinema access required')

    now = int(time.time())
    if now - int(entry.get('ts') or 0) > 24 * 60 * 60:
        _kinopub_stream_tokens.pop(token, None)
        raise web.HTTPForbidden(text='Expired KinoPub stream token')
    entry['ts'] = now

    url = str(entry.get('url') or '').strip()
    parsed = urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.netloc:
        raise web.HTTPBadRequest(text='Invalid upstream URL')

    upstream_headers = {'User-Agent':'AbajTV/1.0','Accept':request.headers.get('Accept','*/*')}
    for name in ('Range','If-Range','If-Modified-Since','If-None-Match'):
        value = request.headers.get(name)
        if value:
            upstream_headers[name] = value

    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_connect=10, sock_read=45)
    session = aiohttp.ClientSession(timeout=timeout, headers=upstream_headers)
    upstream = None
    try:
        upstream = await session.get(url, allow_redirects=True)
        ctype = str(upstream.headers.get('Content-Type') or '').lower()
        final_url = str(upstream.url)
        is_hls = 'mpegurl' in ctype or final_url.lower().split('?',1)[0].endswith('.m3u8')

        if is_hls:
            body = await upstream.read()
            text = body.decode('utf-8','ignore')
            if '#EXTM3U' in text[:4096]:
                rewritten = _rewrite_kinopub_hls(text, final_url, request, uid)
                return web.Response(
                    text=rewritten,
                    status=upstream.status,
                    content_type='application/vnd.apple.mpegurl',
                    headers={'Cache-Control':'no-store'}
                )
            return web.Response(
                body=body,
                status=upstream.status,
                headers={
                    'Content-Type': upstream.headers.get('Content-Type','application/octet-stream'),
                    'Cache-Control':'private, max-age=10',
                }
            )

        response_headers = {'Cache-Control':'private, max-age=30'}
        for name in ('Content-Type','Content-Length','Content-Range','Accept-Ranges','ETag','Last-Modified','Content-Disposition'):
            value = upstream.headers.get(name)
            if value:
                response_headers[name] = value

        resp = web.StreamResponse(status=upstream.status, headers=response_headers)
        await resp.prepare(request)
        try:
            async for chunk in upstream.content.iter_chunked(128 * 1024):
                await resp.write(chunk)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        try:
            await resp.write_eof()
        except Exception:
            pass
        return resp
    except aiohttp.ClientError as exc:
        raise web.HTTPBadGateway(text='KinoPub upstream failed') from exc
    finally:
        if upstream is not None:
            upstream.close()
        await session.close()


def _kinopub_media_array(value):
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [x for x in value.values() if isinstance(x, dict)]
    return []

def _kinopub_media_rows(item):
    rows=[]
    videos=_kinopub_media_array(item.get('videos') if isinstance(item,dict) else None)
    if videos:
        rows.append({'title':'Фильм' if len(videos)==1 else 'Видео','items':videos})
    seasons=item.get('seasons') if isinstance(item,dict) else None
    if isinstance(seasons,list):
        for idx,season in enumerate(seasons):
            if not isinstance(season,dict):
                continue
            episodes=_kinopub_media_array(season.get('episodes'))
            if not episodes:
                episodes=_kinopub_media_array(season.get('videos'))
            if not episodes:
                continue
            season_number=season.get('number')
            normalized=[]
            for ep in episodes:
                row=dict(ep)
                if row.get('season') is None and season_number is not None:
                    row['season']=season_number
                normalized.append(row)
            rows.append({
                'title':str(season.get('title') or f'Сезон {season_number if season_number is not None else idx+1}'),
                'season':season_number if season_number is not None else idx+1,
                'items':normalized,
            })
    if not rows and isinstance(item,dict) and isinstance(item.get('files'),list):
        rows.append({'title':'Фильм','items':[item]})
    return rows

def _kinopub_trailer_url(item):
    if not isinstance(item, dict):
        return ''
    direct_keys = ('trailer','trailer_url','trailerUrl','youtube','youtube_url','youtubeUrl','video_trailer')
    for key in direct_keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for sub in ('url','link','embed','embedUrl','src','youtube','id'):
                v = value.get(sub)
                if isinstance(v, str) and v.strip():
                    if sub == 'id' and re.fullmatch(r'[A-Za-z0-9_-]{6,}', v.strip()):
                        return 'https://www.youtube.com/watch?v=' + v.strip()
                    return v.strip()
        if isinstance(value, list):
            for row in value:
                if isinstance(row, str) and row.strip():
                    return row.strip()
                if isinstance(row, dict):
                    for sub in ('url','link','embed','embedUrl','src','youtube','id'):
                        v = row.get(sub)
                        if isinstance(v, str) and v.strip():
                            if sub == 'id' and re.fullmatch(r'[A-Za-z0-9_-]{6,}', v.strip()):
                                return 'https://www.youtube.com/watch?v=' + v.strip()
                            return v.strip()
    for key, value in item.items():
        if 'trailer' not in str(key).lower() and 'youtube' not in str(key).lower():
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''

def _kinopub_media_summary(media):
    if not isinstance(media,dict):
        return {}
    return {
        'id': media.get('media_id') or media.get('mid') or media.get('id'),
        'number': media.get('number'),
        'season': media.get('season'),
        'title': media.get('title') or media.get('name'),
        'duration': media.get('duration'),
        'watching': media.get('watching'),
        'files': media.get('files') if isinstance(media.get('files'),list) else [],
        'audios': media.get('audios') if isinstance(media.get('audios'),list) else [],
        'subtitles': media.get('subtitles') if isinstance(media.get('subtitles'),list) else [],
    }

async def api_kinopub_item(request):
    user=await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'},status=401)
    uid=int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'},status=403)
    token=await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'},status=401)
    item_id=str(request.query.get('id') or '').strip()
    if not item_id:
        return web.json_response({'ok':False,'error':'missing_item_id'},status=400)
    status,item_payload=await _kinopub_api('GET','/v1/items/'+item_id,params={'access_token':token})
    if status>=400 or not isinstance(item_payload,dict):
        return web.json_response({'ok':False,'error':'kinopub_item_failed','status':status},status=502)
    item=item_payload.get('item') if isinstance(item_payload.get('item'),dict) else item_payload
    rows=[]
    for row in _kinopub_media_rows(item):
        rows.append({
            'title':row.get('title'),
            'season':row.get('season'),
            'items':[_kinopub_media_summary(x) for x in row.get('items',[]) if isinstance(x,dict)],
        })
    related = []
    for key in ('similar','related','recommendations','recommended','also_watch','watch_also'):
        value = item.get(key) if isinstance(item,dict) else None
        if isinstance(value, dict):
            value = value.get('items') or value.get('results') or value.get('data')
        if not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            normalized = _kinopub_normalize(row)
            if normalized:
                related.append(normalized)
        if related:
            break
    if not related:
        try:
            sim_status, sim_data = await _kinopub_api('GET','/v1/items/similar',params={'access_token':token,'id':item_id})
            if sim_status < 400:
                for row in _kinopub_extract_items(sim_data):
                    normalized = _kinopub_normalize(row)
                    if normalized:
                        related.append(normalized)
        except Exception:
            pass

    normalized_item=_kinopub_normalize(item) or {'id':item_id,'title':str(item.get('title') or '')}
    # Lightweight diagnostics: expose metadata shape without credentials or raw source payloads.
    # This helps distinguish missing upstream portraits from broken image rendering.
    if _is_admin_user(user):
        raw_cast = item.get('actors') or item.get('cast') or item.get('actor') or []
        cast_fields = sorted(set(raw_cast[0].keys())) if isinstance(raw_cast, list) and raw_cast and isinstance(raw_cast[0], dict) else []
        normalized_item['cast_diagnostics'] = {
            'source': 'KINOPUB',
            'cast_format': 'objects' if cast_fields else ('text' if isinstance(raw_cast, str) else 'list'),
            'cast_count': len(normalized_item.get('actor_cards') or []),
            'photo_count': sum(bool(x.get('image')) for x in normalized_item.get('actor_cards') or []),
            'actor_fields': cast_fields[:32],
        }

    return web.json_response({
        'ok':True,
        'item':normalized_item,
        'media_rows':rows,
        'related':related[:24],
    },headers={'Cache-Control':'private, max-age=300'})

async def api_kinopub_play(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_playback_allowed(uid):
        return web.json_response({'ok':False,'error':'subscription_required'}, status=403)
    token = await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)
    item_id = str(request.query.get('id') or '').strip()
    media_id = str(request.query.get('mid') or '').strip()
    file_token = str(request.query.get('file') or '').strip()
    requested_format = str(request.query.get('format') or '').strip().lower()
    stream_types = ('http','hls4','hls2','hls') if requested_format == 'http' else ('hls4','hls2','hls','http')
    if file_token:
        for stream_type in stream_types:
            st, video = await _kinopub_api('GET','/v1/items/media-video-link',params={
                'access_token':token,'file':file_token,'type':stream_type
            })
            if st < 400:
                direct = _kinopub_stream_from_obj(video)
                if direct:
                    response = _kinopub_direct_stream_response(request, uid, direct)
                    if response is not None:
                        return response
    if media_id:
        status, media = await _kinopub_api('GET','/v1/items/media-links',params={'access_token':token,'mid':media_id})
        if status < 400:
            resolved_file = _kinopub_first_file_token(media)
            if resolved_file:
                for stream_type in stream_types:
                    st, video = await _kinopub_api('GET','/v1/items/media-video-link',params={
                        'access_token':token,'file':resolved_file,'type':stream_type
                    })
                    if st < 400:
                        direct = _kinopub_stream_from_obj(video)
                        if direct:
                            response = _kinopub_direct_stream_response(request, uid, direct)
                            if response is not None:
                                return response
            if requested_format != 'http':
                for obj in _kinopub_walk(media):
                    direct = _kinopub_stream_from_obj(obj)
                    if direct:
                        response = _kinopub_direct_stream_response(request, uid, direct)
                        if response is not None:
                            return response
    if not item_id:
        return web.json_response({'ok':False,'error':'missing_item_id'}, status=400)

    status, item_payload = await _kinopub_api('GET', '/v1/items/' + item_id, params={'access_token':token})
    if status >= 400:
        return web.json_response({'ok':False,'error':'kinopub_item_failed','status':status}, status=502)
    item = item_payload.get('item') if isinstance(item_payload,dict) and isinstance(item_payload.get('item'),dict) else item_payload

    media_id = _kinopub_first_media_id(item)
    file_token = _kinopub_first_file_token(item)

    if media_id:
        status, media = await _kinopub_api('GET','/v1/items/media-links',params={'access_token':token,'mid':media_id})
        if status < 400:
            resolved_file = _kinopub_first_file_token(media)
            if resolved_file:
                file_token = resolved_file
            if requested_format != 'http':
                for obj in _kinopub_walk(media):
                    direct = _kinopub_stream_from_obj(obj)
                    if direct:
                        response = _kinopub_direct_stream_response(request, uid, direct)
                        if response is not None:
                            return response

    if file_token:
        for stream_type in stream_types:
            st, video = await _kinopub_api('GET','/v1/items/media-video-link',params={
                'access_token':token,'file':file_token,'type':stream_type
            })
            if st < 400:
                direct = _kinopub_stream_from_obj(video)
                if direct:
                    response = _kinopub_direct_stream_response(request, uid, direct)
                    if response is not None:
                        return response

    return web.json_response({'ok':False,'error':'kinopub_stream_not_found'}, status=404)

async def api_kinopub_benchmark(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_playback_allowed(uid):
        return web.json_response({'ok':False,'error':'subscription_required'}, status=403)
    token = await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)
    media_id = str(request.query.get('mid') or '').strip()
    if not media_id:
        return web.json_response({'ok':False,'error':'missing_media_id'}, status=400)

    status, media = await _kinopub_api('GET','/v1/items/media-links',params={'access_token':token,'mid':media_id})
    if status >= 400:
        return web.json_response({'ok':False,'error':'media_links_failed','status':status}, status=502)
    file_token = _kinopub_first_file_token(media)
    if not file_token:
        return web.json_response({'ok':False,'error':'file_token_not_found'}, status=404)

    direct = ''
    chosen_type = ''
    for stream_type in ('http','hls4','hls2','hls'):
        st, video = await _kinopub_api('GET','/v1/items/media-video-link',params={
            'access_token':token,'file':file_token,'type':stream_type
        })
        if st < 400:
            direct = _kinopub_stream_from_obj(video)
            if direct:
                chosen_type = stream_type
                break
    if not direct:
        return web.json_response({'ok':False,'error':'stream_not_found'}, status=404)

    proxied = _kinopub_proxy_url(request, uid, direct)

    async def sample(url, range_header='bytes=0-2097151'):
        started = time.perf_counter()
        first_byte_ms = None
        total = 0
        status_code = 0
        ctype = ''
        content_range = ''
        content_length = ''
        accept_ranges = ''
        timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
        headers = {'Range':range_header,'Accept':'*/*'}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    status_code = int(resp.status)
                    ctype = str(resp.headers.get('Content-Type') or '')[:80]
                    content_range = str(resp.headers.get('Content-Range') or '')[:120]
                    content_length = str(resp.headers.get('Content-Length') or '')[:40]
                    accept_ranges = str(resp.headers.get('Accept-Ranges') or '')[:40]
                    async for chunk in resp.content.iter_chunked(65536):
                        if first_byte_ms is None:
                            first_byte_ms = round((time.perf_counter()-started)*1000)
                        total += len(chunk)
                        if total >= 2097152:
                            break
            elapsed = max(0.001, time.perf_counter()-started)
            return {
                'ok': 200 <= status_code < 400,
                'status': status_code,
                'first_byte_ms': first_byte_ms,
                'elapsed_ms': round(elapsed*1000),
                'bytes': total,
                'mbps': round((total*8/1000000)/elapsed, 2),
                'content_type': ctype,
                'content_range': content_range,
                'content_length': content_length,
                'accept_ranges': accept_ranges,
                'requested_range': range_header,
            }
        except Exception as exc:
            return {
                'ok': False,
                'status': status_code,
                'first_byte_ms': first_byte_ms,
                'elapsed_ms': round((time.perf_counter()-started)*1000),
                'bytes': total,
                'mbps': 0,
                'content_range': content_range,
                'content_length': content_length,
                'accept_ranges': accept_ranges,
                'requested_range': range_header,
                'error': type(exc).__name__+': '+str(exc)[:120],
            }

    direct_result, proxy_result, direct_mid, proxy_mid = await asyncio.gather(
        sample(direct,'bytes=0-2097151'),
        sample(proxied,'bytes=0-2097151'),
        sample(direct,'bytes=52428800-54525951'),
        sample(proxied,'bytes=52428800-54525951'),
    )
    return web.json_response({
        'ok': True,
        'mid': media_id,
        'stream_type': chosen_type,
        'direct_host': urlparse(direct).hostname or '',
        'proxy_host': urlparse(proxied).hostname or '',
        'direct': direct_result,
        'proxy': proxy_result,
        'direct_mid': direct_mid,
        'proxy_mid': proxy_mid,
    }, headers={'Cache-Control':'no-store'})

async def api_kinopub_download(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_playback_allowed(uid):
        return web.json_response({'ok':False,'error':'subscription_required'}, status=403)
    token = await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)

    item_id = str(request.query.get('id') or '').strip()
    media_id = str(request.query.get('mid') or '').strip()
    if not item_id and not media_id:
        return web.json_response({'ok':False,'error':'missing_item_id'}, status=400)

    file_token = ''
    if media_id:
        status, media = await _kinopub_api('GET','/v1/items/media-links',params={
            'access_token':token,'mid':media_id
        })
        if status < 400:
            file_token = _kinopub_first_file_token(media)

    if not file_token and item_id:
        status, item_payload = await _kinopub_api('GET','/v1/items/' + item_id, params={
            'access_token':token
        })
        if status >= 400:
            return web.json_response({'ok':False,'error':'kinopub_item_failed','status':status}, status=502)
        item = item_payload.get('item') if isinstance(item_payload,dict) and isinstance(item_payload.get('item'),dict) else item_payload
        file_token = _kinopub_first_file_token(item)
        if not file_token:
            resolved_mid = _kinopub_first_media_id(item)
            if resolved_mid:
                status, media = await _kinopub_api('GET','/v1/items/media-links',params={
                    'access_token':token,'mid':resolved_mid
                })
                if status < 400:
                    file_token = _kinopub_first_file_token(media)

    if not file_token:
        return web.json_response({'ok':False,'error':'kinopub_download_not_found'}, status=404)

    status, video = await _kinopub_api('GET','/v1/items/media-video-link',params={
        'access_token':token,'file':file_token,'type':'http'
    })
    if status >= 400:
        return web.json_response({'ok':False,'error':'kinopub_download_failed','status':status}, status=502)
    direct = _kinopub_stream_from_obj(video)
    if not direct or not direct.startswith(('http://','https://')):
        return web.json_response({'ok':False,'error':'kinopub_download_not_found'}, status=404)

    return web.json_response({
        'ok':True,
        'url':direct,
        'provider':'KINOPUB',
        'download':True,
    }, headers={'Cache-Control':'no-store'})

async def api_kinopub_overview(request):
    user = await _user_from_request(request)
    token = await _public_cinema_token(user)
    if not token:
        return web.json_response({'ok':False,'error':'catalog_source_unavailable'}, status=503)
    async def total_for(type_name):
        status, data = await _kinopub_api('GET','/v1/items',params={
            'access_token':token,'type':type_name,'perpage':1,'page':0,'sort':'updated-'
        })
        if status >= 400:
            return None
        total = _kinopub_total_from_data(data)
        if total is not None:
            return total
        return len(_kinopub_extract_items(data))

    movies_total, series_total = await asyncio.gather(total_for('movie'), total_for('serial'))
    return web.json_response({
        'ok':True,
        'movies_total':movies_total,
        'series_total':series_total,
        'total':(movies_total + series_total) if isinstance(movies_total,int) and isinstance(series_total,int) else None,
    }, headers={'Cache-Control':'private, max-age=300'})

def _cinema_library_key(uid, section):
    return f'cinema_library:{int(uid)}:{section}'

async def _cinema_library_read(uid, section):
    raw = await get_setting(_cinema_library_key(uid, section), '[]')
    try:
        rows = json.loads(raw or '[]')
    except Exception:
        rows = []
    return [x for x in rows if isinstance(x, dict)]

async def _cinema_library_write(uid, section, rows):
    await set_setting(_cinema_library_key(uid, section), json.dumps(rows, ensure_ascii=False, separators=(',',':')))

async def api_cinema_progress(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    if request.method == 'GET':
        item_id = str(request.query.get('item_id') or '').strip()
        media_id = str(request.query.get('media_id') or '').strip()
        if not item_id:
            return web.json_response({'ok':False,'error':'missing_item_id'}, status=400)
        raw = await get_setting(f'cinema_progress:{uid}:{item_id}:{media_id}', '')
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        return web.json_response({'ok':True,'progress':data}, headers={'Cache-Control':'no-store'})
    try:
        body = await request.json()
    except Exception:
        body = {}
    item_id = str(body.get('item_id') or '').strip()
    media_id = str(body.get('media_id') or '').strip()
    if not item_id:
        return web.json_response({'ok':False,'error':'missing_item_id'}, status=400)
    try:
        position = max(0.0, float(body.get('position') or 0))
        duration = max(0.0, float(body.get('duration') or 0))
    except Exception:
        position, duration = 0.0, 0.0
    completed = bool(duration > 0 and position / duration >= 0.96)
    if completed:
        position = 0.0
    season = body.get('season') if isinstance(body,dict) else None
    episode = body.get('episode') if isinstance(body,dict) else None
    data = {
        'item_id':item_id,
        'media_id':media_id,
        'position':round(position,2),
        'duration':round(duration,2),
        'completed':completed,
        'season':season,
        'episode':episode,
        'updated_at':int(time.time()),
    }
    await set_setting(f'cinema_progress:{uid}:{item_id}:{media_id}', json.dumps(data,separators=(',',':')))

    watching = await _cinema_library_read(uid, 'watching')
    changed = False
    next_rows = []
    for row in watching:
        if str(row.get('id') or '').strip() == item_id:
            row = dict(row)
            is_series = str(row.get('kind') or '').lower() in ('series','serial')
            if completed and not is_series:
                changed = True
                continue
            row['position'] = data['position']
            row['duration'] = data['duration']
            row['media_id'] = media_id
            if season is not None:
                row['season'] = season
            if episode is not None:
                row['episode'] = episode
            row['completed_media_id'] = media_id if completed else ''
            row['updated_at'] = data['updated_at']
            changed = True
        next_rows.append(row)
    if changed:
        await _cinema_library_write(uid, 'watching', next_rows[:100])

    return web.json_response({'ok':True,'progress':data}, headers={'Cache-Control':'no-store'})

async def _kinopub_bookmark_folders(uid: int):
    token = await _kinopub_access_token(uid)
    if not token:
        return token, []
    status, data = await _kinopub_api('GET', '/v1/bookmarks', params={'access_token': token})
    if status >= 400 or not isinstance(data, dict):
        return token, []

    rows = []
    candidates = []
    for key in ('bookmarks', 'folders', 'items', 'data'):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get('items') or value.get('bookmarks') or value.get('folders') or []
        if isinstance(value, list):
            candidates.extend(value)
    seen = set()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        folder_id = str(row.get('id') or row.get('bookmark_id') or row.get('folder_id') or '').strip()
        if not folder_id or folder_id in seen:
            continue
        seen.add(folder_id)
        title = str(row.get('title') or row.get('name') or row.get('label') or 'Избранное').strip()
        count = row.get('count')
        if count is None:
            count = row.get('items_count')
        if count is None:
            count = row.get('total')
        try:
            count = max(0, int(count or 0))
        except Exception:
            count = 0
        rows.append({'id':folder_id,'title':title,'count':count,'kind':'bookmark_folder','source':'KINOPUB'})
    return token, rows


async def _kinopub_bookmark_folder_items(token: str, folder_id: str):
    synced = []
    seen = set()
    for page in range(1, 11):
        st, payload = await _kinopub_api('GET', '/v1/bookmarks/' + folder_id, params={
            'access_token': token, 'page': page, 'perpage': 100,
        })
        if st >= 400:
            break
        raw_items = _kinopub_extract_items(payload)
        if not raw_items:
            break
        added_on_page = 0
        for raw in raw_items:
            item = _kinopub_normalize(raw)
            if not item:
                continue
            key = str(item.get('id') or '').strip() or str(item.get('title') or '').strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            compact = {k:item.get(k) for k in ('id','title','original_title','year','poster','description','rating','kind','source') if item.get(k) is not None}
            compact['saved_at'] = int(time.time())
            synced.append(compact)
            added_on_page += 1
        if len(raw_items) < 100 or added_on_page == 0:
            break
    return synced[:300]


async def _kinopub_sync_bookmarks(uid: int):
    token, folders = await _kinopub_bookmark_folders(uid)
    if not token:
        return []
    merged = []
    seen = set()
    for folder in folders[:30]:
        for item in await _kinopub_bookmark_folder_items(token, str(folder.get('id') or '')):
            key = str(item.get('id') or '').strip() or str(item.get('title') or '').strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged[:300]


async def api_cinema_library(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    section = str(request.query.get('section') or 'history').strip().lower()
    if section not in ('history','watching','bookmarks'):
        return web.json_response({'ok':False,'error':'bad_section'}, status=400)
    rows = await _cinema_library_read(uid, section)
    if section == 'bookmarks':
        try:
            token, folders = await _kinopub_bookmark_folders(uid)
            folder_id = str(request.query.get('folder') or '').strip()
            flat = str(request.query.get('flat') or '').strip().lower() in ('1','true','yes')
            if folder_id and token:
                remote = await _kinopub_bookmark_folder_items(token, folder_id)
                return web.json_response({'ok':True,'section':section,'folder':folder_id,'items':remote,'count':len(remote)}, headers={'Cache-Control':'no-store'})
            if folders and not flat:
                total = sum(int(x.get('count') or 0) for x in folders)
                return web.json_response({'ok':True,'section':section,'folders':folders,'items':[],'count':total,'folder_count':len(folders)}, headers={'Cache-Control':'no-store'})
            remote = await _kinopub_sync_bookmarks(uid)
            if remote:
                merged = []
                seen = set()
                for item in remote + rows:
                    key = str(item.get('id') or '').strip() or str(item.get('title') or '').strip().casefold()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    merged.append(item)
                rows = merged[:300]
                await _cinema_library_write(uid, 'bookmarks', rows)
        except Exception as exc:
            logging.warning('KINOPUB_BOOKMARK_SYNC failed uid=%s error=%s', uid, type(exc).__name__)
    return web.json_response({'ok':True,'section':section,'items':rows,'count':len(rows)}, headers={'Cache-Control':'no-store'})

async def api_cinema_bookmark_folders(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    token, folders = await _kinopub_bookmark_folders(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_not_connected'}, status=409)

    if request.method == 'GET':
        item_id = str(request.query.get('item_id') or '').strip()
        visible = folders[:30]
        results = []
        if item_id and visible:
            results = await asyncio.gather(*[
                _kinopub_bookmark_folder_items(token, str(folder.get('id') or '')) for folder in visible
            ], return_exceptions=True)
        out = []
        for index, folder in enumerate(visible):
            row = dict(folder)
            row['selected'] = False
            if item_id and index < len(results) and isinstance(results[index], list):
                row['selected'] = any(str(x.get('id') or '').strip() == item_id for x in results[index])
            out.append(row)
        return web.json_response({'ok':True,'folders':out}, headers={'Cache-Control':'no-store'})

    body = await request.json()
    item = body.get('item') if isinstance(body,dict) else None
    selected = body.get('folders') if isinstance(body,dict) else None
    original = body.get('original') if isinstance(body,dict) else None
    create_title = str(body.get('create_title') or '').strip() if isinstance(body,dict) else ''
    if not isinstance(item,dict):
        return web.json_response({'ok':False,'error':'bad_request'}, status=400)
    item_id = str(item.get('id') or '').strip()
    if not item_id or not item_id.isdigit():
        return web.json_response({'ok':False,'error':'bad_item'}, status=400)

    if create_title:
        create_title = create_title[:80]
        status, data = await _kinopub_api(
            'POST',
            '/v1/bookmarks/create',
            params={'access_token': token},
            form_body={'title': create_title},
        )
        if status >= 400 or (isinstance(data,dict) and data.get('error')):
            status, data = await _kinopub_api(
                'POST',
                '/v1/bookmarks/create',
                params={'access_token': token},
                form_body={'name': create_title},
            )
        if status >= 400 or (isinstance(data,dict) and data.get('error')):
            return web.json_response({'ok':False,'error':'kinopub_folder_create_failed'}, status=502)
        _, fresh_folders = await _kinopub_bookmark_folders(uid)
        created = next((x for x in fresh_folders if str(x.get('title') or '').strip().casefold() == create_title.casefold()), None)
        if not created:
            return web.json_response({'ok':False,'error':'kinopub_folder_not_found_after_create'}, status=502)
        folder_id = str(created.get('id') or '').strip()
        if not folder_id.isdigit():
            return web.json_response({'ok':False,'error':'kinopub_folder_bad_id'}, status=502)
        add_status, add_data = await _kinopub_api(
            'POST',
            '/v1/bookmarks/add',
            params={'access_token': token},
            form_body={'item': int(item_id), 'folder': int(folder_id)},
        )
        if add_status >= 400 or (isinstance(add_data,dict) and add_data.get('error')):
            return web.json_response({'ok':False,'error':'kinopub_bookmark_update_failed'}, status=502)
        rows = await _cinema_library_read(uid, 'bookmarks')
        key = item_id
        rows = [x for x in rows if (str(x.get('id') or '').strip() or str(x.get('title') or '').strip().casefold()) != key]
        compact = {k:item.get(k) for k in ('id','title','original_title','year','poster','description','rating','kind','source') if item.get(k) is not None}
        compact['saved_at'] = int(time.time())
        rows.insert(0, compact)
        await _cinema_library_write(uid, 'bookmarks', rows[:300])
        return web.json_response({'ok':True,'added':True,'created_folder':created}, headers={'Cache-Control':'no-store'})

    if not isinstance(selected,list):
        return web.json_response({'ok':False,'error':'bad_request'}, status=400)
    selected_ids = {str(x).strip() for x in selected if str(x).strip()}
    valid_ids = {str(x.get('id') or '').strip() for x in folders}
    selected_ids &= valid_ids
    original_ids = {str(x).strip() for x in original if str(x).strip()} if isinstance(original,list) else None
    if original_ids is not None:
        original_ids &= valid_ids
    changed = 0
    errors = []
    for folder in folders[:30]:
        folder_id = str(folder.get('id') or '').strip()
        if not folder_id or not folder_id.isdigit():
            continue
        if original_ids is not None:
            current = folder_id in original_ids
        else:
            current = False
            try:
                items = await _kinopub_bookmark_folder_items(token, folder_id)
                current = any(str(x.get('id') or '').strip() == item_id for x in items)
            except Exception:
                pass
        wanted = folder_id in selected_ids
        if current == wanted:
            continue
        endpoint = '/v1/bookmarks/add' if wanted else '/v1/bookmarks/remove-item'
        status, data = await _kinopub_api(
            'POST',
            endpoint,
            params={'access_token': token},
            form_body={'item': int(item_id), 'folder': int(folder_id)},
        )
        if status >= 400 or (isinstance(data,dict) and data.get('error')):
            errors.append(folder_id)
        else:
            changed += 1
    if errors:
        return web.json_response({'ok':False,'error':'kinopub_bookmark_update_failed','folders':errors}, status=502)

    rows = await _cinema_library_read(uid, 'bookmarks')
    key = item_id
    rows = [x for x in rows if (str(x.get('id') or '').strip() or str(x.get('title') or '').strip().casefold()) != key]
    if selected_ids:
        compact = {k:item.get(k) for k in ('id','title','original_title','year','poster','description','rating','kind','source') if item.get(k) is not None}
        compact['saved_at'] = int(time.time())
        rows.insert(0, compact)
    await _cinema_library_write(uid, 'bookmarks', rows[:300])
    return web.json_response({'ok':True,'added':bool(selected_ids),'selected':sorted(selected_ids),'changed':changed}, headers={'Cache-Control':'no-store'})


async def api_cinema_library_bookmark(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    body = await request.json()
    item = body.get('item') if isinstance(body,dict) else None
    media_id = str(body.get('media_id') or '').strip() if isinstance(body,dict) else ''
    season = body.get('season') if isinstance(body,dict) else None
    episode = body.get('episode') if isinstance(body,dict) else None
    if not isinstance(item,dict):
        return web.json_response({'ok':False,'error':'bad_item'}, status=400)
    item_id = str(item.get('id') or '').strip()
    title = str(item.get('title') or '').strip()
    if not item_id and not title:
        return web.json_response({'ok':False,'error':'bad_item'}, status=400)
    rows = await _cinema_library_read(uid, 'bookmarks')
    key = item_id or title.casefold()
    existing = next((i for i,x in enumerate(rows) if (str(x.get('id') or '').strip() or str(x.get('title') or '').strip().casefold()) == key), -1)
    added = existing < 0
    if added:
        compact = {k:item.get(k) for k in ('id','title','original_title','year','poster','description','rating','kind','source') if item.get(k) is not None}
        compact['saved_at'] = int(time.time())
        rows.insert(0, compact)
    else:
        rows.pop(existing)
    rows = rows[:300]
    await _cinema_library_write(uid, 'bookmarks', rows)
    return web.json_response({'ok':True,'added':added,'count':len(rows)}, headers={'Cache-Control':'no-store'})

_cinema_rating_locks = {}

async def api_cinema_rating(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])

    if request.method == 'GET':
        item_id = str(request.query.get('item_id') or '').strip()
        if not item_id or len(item_id) > 80:
            return web.json_response({'ok':False,'error':'bad_item'}, status=400)
        raw = await get_setting('cinema_rating:' + item_id, '')
        try:
            votes = json.loads(raw or '{}')
        except Exception:
            votes = {}
        if not isinstance(votes, dict):
            votes = {}
        clean = []
        mine = 0
        for key, value in votes.items():
            try:
                score = int(value)
            except Exception:
                continue
            if 1 <= score <= 10:
                clean.append(score)
                if str(key) == str(uid):
                    mine = score
        average = round(sum(clean) / len(clean), 1) if clean else 0
        return web.json_response({
            'ok':True,
            'item_id':item_id,
            'average':average,
            'count':len(clean),
            'mine':mine,
        }, headers={'Cache-Control':'no-store'})

    try:
        body = await request.json()
    except Exception:
        body = {}
    item_id = str(body.get('item_id') or '').strip()
    try:
        score = int(body.get('score') or 0)
    except Exception:
        score = 0
    if not item_id or len(item_id) > 80 or score < 1 or score > 10:
        return web.json_response({'ok':False,'error':'bad_request'}, status=400)

    lock = _cinema_rating_locks.setdefault(item_id, asyncio.Lock())
    async with lock:
        raw = await get_setting('cinema_rating:' + item_id, '')
        try:
            votes = json.loads(raw or '{}')
        except Exception:
            votes = {}
        if not isinstance(votes, dict):
            votes = {}
        votes[str(uid)] = score
        clean_votes = {}
        clean_scores = []
        for key, value in votes.items():
            try:
                current = int(value)
            except Exception:
                continue
            if 1 <= current <= 10:
                clean_votes[str(key)] = current
                clean_scores.append(current)
        await set_setting('cinema_rating:' + item_id, json.dumps(clean_votes, separators=(',', ':')))
        average = round(sum(clean_scores) / len(clean_scores), 1) if clean_scores else 0

    return web.json_response({
        'ok':True,
        'item_id':item_id,
        'average':average,
        'count':len(clean_scores),
        'mine':score,
    }, headers={'Cache-Control':'no-store'})


async def api_cinema_library_watch(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    body = await request.json()
    item = body.get('item') if isinstance(body,dict) else None
    if not isinstance(item,dict):
        return web.json_response({'ok':False,'error':'bad_item'}, status=400)
    item_id = str(item.get('id') or '').strip()
    title = str(item.get('title') or '').strip()
    if not item_id and not title:
        return web.json_response({'ok':False,'error':'bad_item'}, status=400)
    media_id = str(body.get('media_id') or '').strip() if isinstance(body,dict) else ''
    season = body.get('season') if isinstance(body,dict) else None
    episode = body.get('episode') if isinstance(body,dict) else None
    key = item_id or title.casefold()
    compact = {k:item.get(k) for k in ('id','title','original_title','year','poster','description','rating','kind','source') if item.get(k) is not None}
    compact['watched_at'] = int(time.time())
    if media_id:
        compact['media_id'] = media_id
    if season is not None:
        compact['season'] = season
    if episode is not None:
        compact['episode'] = episode
    for section, limit in (('history',200),('watching',100)):
        rows = await _cinema_library_read(uid, section)
        rows = [x for x in rows if (str(x.get('id') or '').strip() or str(x.get('title') or '').strip().casefold()) != key]
        rows.insert(0, dict(compact))
        await _cinema_library_write(uid, section, rows[:limit])
    return web.json_response({'ok':True}, headers={'Cache-Control':'no-store'})

def _kinopub_extract_references(data):
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = []
        for key in ('items','results','data','genres','types'):
            value = data.get(key)
            if isinstance(value, list):
                rows = value
                break
            if isinstance(value, dict):
                for subkey in ('items','results','data'):
                    nested = value.get(subkey)
                    if isinstance(nested, list):
                        rows = nested
                        break
                if rows:
                    break
    else:
        rows = []
    out = []
    for row in rows:
        if isinstance(row, dict):
            rid = row.get('id')
            title = row.get('title') or row.get('name')
            if rid is None or not str(title or '').strip():
                continue
            out.append({'id':str(rid),'title':str(title).strip()})
        elif isinstance(row, str) and row.strip():
            out.append({'id':row.strip(),'title':row.strip()})
    return out

async def api_kinopub_filters(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    token = await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)
    requested_type = str(request.query.get('type') or '').strip()
    type_param = 'serial' if requested_type in ('series','serial') else ('movie' if requested_type in ('movies','movie') else '')
    async def fetch_ref(path, params=None):
        status, data = await _kinopub_api('GET', path, params={'access_token':token, **(params or {})})
        return _kinopub_extract_references(data) if status < 400 else []
    types, genres = await asyncio.gather(
        fetch_ref('/v1/types'),
        fetch_ref('/v1/genres', {'type':type_param} if type_param else {})
    )
    return web.json_response({'ok':True,'types':types,'genres':genres}, headers={'Cache-Control':'private, max-age=1800'})

_kinopub_genres_cache = {'ts':0, 'items':[]}

async def _kinopub_genres(token):
    now = int(time.time())
    cached = _kinopub_genres_cache.get('items') or []
    if cached and now - int(_kinopub_genres_cache.get('ts') or 0) < 1800:
        return cached
    status, data = await _kinopub_api('GET', '/v1/genres', params={'access_token':token})
    if status >= 400:
        return cached
    items = _kinopub_extract_references(data)
    clean = []
    for row in items:
        if not isinstance(row, dict):
            continue
        gid = str(row.get('id') or '').strip()
        title = str(row.get('title') or row.get('name') or '').strip()
        if gid and title:
            clean.append({'id':gid, 'title':title, 'type':str(row.get('type') or '').strip()})
    if clean:
        _kinopub_genres_cache['ts'] = now
        _kinopub_genres_cache['items'] = clean
    return clean

async def _kinopub_genre_ids(token, section):
    rows = await _kinopub_genres(token)
    ids = []
    for row in rows:
        title = str(row.get('title') or '').strip().lower()
        if section == 'anime':
            match = any(x in title for x in ('аниме','anime'))
        elif section == 'cartoons':
            match = any(x in title for x in ('мульт','cartoon','animation','animated')) and not any(x in title for x in ('аниме','anime'))
        else:
            match = False
        if match:
            gid = str(row.get('id') or '').strip()
            if gid and gid not in ids:
                ids.append(gid)
    return ids

def _kinopub_filter_section_rows(rows, section, requested_type=''):
    out = []
    requested_type = str(requested_type or '').strip().lower()
    for row in rows:
        group = str(row.get('group') or '').strip().lower()
        raw_type = str(row.get('raw_type') or '').strip().lower()
        kind = str(row.get('kind') or '').strip().lower()

        if section == 'cartoons' and group != 'cartoons':
            continue
        if section == 'anime' and group != 'anime':
            continue
        if section == 'movies' and (kind != 'movies' or group in ('anime','cartoons')):
            continue
        if section == 'series' and (kind != 'series' or group in ('anime','cartoons')):
            continue
        if section == 'docmovies' and raw_type not in ('documovie','documentary','docmovie'):
            continue
        if section == 'docseries' and raw_type not in ('docuserial','documentaryseries','docseries'):
            continue
        if section == 'tvshows' and raw_type != 'tvshow':
            continue
        if section == 'concerts' and raw_type != 'concert':
            continue
        if section in ('fresh','popular','hot','4k'):
            if requested_type == 'movie' and (kind != 'movies' or group in ('anime','cartoons')):
                continue
            if requested_type == 'serial' and (kind != 'series' or group in ('anime','cartoons')):
                continue
        out.append(row)
    return out

async def _kinopub_section_page(token, *, path='/v1/items', params=None):
    status, data = await _kinopub_api('GET', path, params={'access_token':token, **(params or {})})
    if status >= 400:
        return status, [], None, data
    rows = []
    for item in _kinopub_extract_items(data):
        row = _kinopub_normalize(item)
        if row:
            rows.append(row)
    return status, rows, _kinopub_total_from_data(data), data

async def _public_cinema_token(user):
    """Read-only catalogue token. Playback endpoints remain subscription guarded."""
    uid = int(user['id']) if user else 0
    if uid:
        token = await _kinopub_access_token(uid)
        if token:
            return token
    try:
        owner = int(str(await get_setting('kinopub_owner_uid', '') or '').strip() or 0)
    except Exception:
        owner = 0
    owner = owner or int(ADMIN_ID or 0)
    return await _kinopub_access_token(owner) if owner else ''
async def api_kinopub_section(request):
    user = await _user_from_request(request)
    token = await _public_cinema_token(user)
    if not token:
        return web.json_response({'ok':False,'error':'catalog_source_unavailable'}, status=503)
    section = str(request.query.get('section') or 'movies').strip().lower()
    sort = str(request.query.get('sort') or '').strip().lower()
    sort = {
        'new':'created-',
        'popular':'views-',
        'hot':'rating-',
    }.get(sort, sort)
    try:
        page = max(1, int(request.query.get('page') or 1))
        perpage = max(12, min(60, int(request.query.get('perpage') or 40)))
    except Exception:
        page, perpage = 1, 40

    if section == 'collections':
        status, data = await _kinopub_api('GET','/v1/collections',params={
            'access_token':token,'page':page,'perpage':perpage,'sort':sort
        })
        if status >= 400:
            return web.json_response({'ok':False,'error':'kinopub_collections_failed','status':status}, status=502)
        raw = _kinopub_extract_items(data)
        rows=[]
        for item in raw:
            title=str(item.get('title') or item.get('name') or '').strip()
            if not title: continue
            rows.append({
                'id':str(item.get('id') or ''),
                'title':title,
                'poster':_kinopub_poster(item),
                'description':str(item.get('description') or item.get('plot') or ''),
                'source':'KINOPUB_COLLECTION',
                'kind':'collection',
            })
        total=_kinopub_total_from_data(data)
        return web.json_response({
            'ok':True,'items':rows,'count':len(rows),'total':total,'page':page,'perpage':perpage,
            'has_more':bool(len(rows)>0 and (total is None or page*perpage<total)),
        },headers={'Cache-Control':'no-store'})

    requested_type = str(request.query.get('type') or '').strip().lower()
    if requested_type in ('series','serial'):
        requested_type = 'serial'
    elif requested_type in ('movies','movie'):
        requested_type = 'movie'
    else:
        requested_type = ''

    mapping = {
        'movies': {'type':'movie'},
        'series': {'type':'serial'},
        'docmovies': {'type':'documovie'},
        'docseries': {'type':'docuserial'},
        'tvshows': {'type':'tvshow'},
        'concerts': {'type':'concert'},
        '4k': {'quality':'4k', **({'type':requested_type} if requested_type else {})},
    }
    shortcut = ''
    if section in ('fresh','popular','hot'):
        shortcut = section
        api_type = requested_type or 'movie'
        params={'type':api_type,'page':page,'perpage':perpage}
        path=f'/v1/items/{shortcut}'
    elif section in ('cartoons','anime'):
        genre_ids = await _kinopub_genre_ids(token, section)
        params={'page':page,'perpage':perpage}
        if genre_ids:
            params['genre'] = ','.join(genre_ids)
        else:
            params['genre'] = 'аниме' if section == 'anime' else 'мультфильм'
        if sort and sort != '4k':
            params['sort'] = sort
        path='/v1/items'
    else:
        params={**mapping.get(section, {'type':'movie'}),'page':page,'perpage':perpage}
        if sort:
            params['sort']=sort
        path='/v1/items'

    status, rows, total, data = await _kinopub_section_page(token,path=path,params=params)
    rows = _kinopub_filter_section_rows(rows, section, requested_type)

    if section in ('fresh','popular','hot') and (status >= 400 or not rows):
        fallback_sort = {
            'fresh':'updated-',
            'popular':'views-',
            'hot':'rating-',
        }.get(section,'updated-')
        fallback_params={
            'type':params.get('type','movie'),
            'page':page,
            'perpage':perpage,
            'sort':fallback_sort,
        }
        fb_status, fb_rows, fb_total, fb_data = await _kinopub_section_page(
            token,path='/v1/items',params=fallback_params
        )
        if fb_status < 400 and fb_rows:
            fb_rows = _kinopub_filter_section_rows(fb_rows, section, requested_type)
            if fb_rows:
                status, rows, total, data = fb_status, fb_rows, fb_total, fb_data

    if status >= 400:
        return web.json_response({'ok':False,'error':'kinopub_section_failed','status':status}, status=502)

    # KinoPub may return a small server-side page even when a larger perpage is requested.
    # Fill the first screen from subsequent pages, capped to keep API work small.
    if page == 1 and len(rows) < min(30, perpage):
        seen={str(x.get('id') or '') for x in rows}
        next_page=2
        while len(rows) < min(40, perpage) and next_page <= 5:
            more_params=dict(params); more_params['page']=next_page
            st, more, _, _ = await _kinopub_section_page(token,path=path,params=more_params)
            if st >= 400 or not more: break
            more = _kinopub_filter_section_rows(more, section, requested_type)
            if not more: break
            added=0
            for x in more:
                key=str(x.get('id') or '')
                if key and key not in seen:
                    seen.add(key); rows.append(x); added+=1
            if not added: break
            next_page += 1

    return web.json_response({
        'ok':True,'items':rows,'count':len(rows),'total':total,'page':page,'perpage':perpage,
        'has_more':bool(len(rows)>0 and (total is None or page*perpage<total)),
    },headers={'Cache-Control':'no-store'})

async def api_kinopub_collection_items(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid=int(user['id'])
    if not await _cinema_access_allowed(uid):
        return web.json_response({'ok':False,'error':'cinema_access_required'}, status=403)
    token=await _kinopub_access_token(uid)
    if not token:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)
    cid=str(request.query.get('id') or '').strip()
    if not cid:
        return web.json_response({'ok':False,'error':'missing_collection_id'}, status=400)
    try: page=max(1,int(request.query.get('page') or 1))
    except Exception: page=1
    status,data=await _kinopub_api('GET','/v1/collections/view',params={'access_token':token,'id':cid,'page':page,'perpage':40})
    if status>=400:
        return web.json_response({'ok':False,'error':'kinopub_collection_failed','status':status}, status=502)
    rows=[]
    for item in _kinopub_extract_items(data):
        row=_kinopub_normalize(item)
        if row: rows.append(row)
    total=_kinopub_total_from_data(data)
    return web.json_response({'ok':True,'items':rows,'count':len(rows),'total':total,'page':page},headers={'Cache-Control':'no-store'})

async def api_kinopub_catalog(request):
    user = await _user_from_request(request)
    token = await _public_cinema_token(user)
    if not token:
        return web.json_response({'ok':False,'error':'catalog_source_unavailable'}, status=503)
    query = str(request.query.get('q') or '').strip()
    actor_query = str(request.query.get('actor') or '').strip()
    requested_kind = str(request.query.get('type') or '').strip().lower()
    genre = str(request.query.get('genre') or '').strip()
    try:
        page = max(1, int(request.query.get('page') or 1))
        perpage = max(12, min(60, int(request.query.get('perpage') or 30)))
    except Exception:
        page, perpage = 1, 30
    path = '/v1/items/search' if query else '/v1/items'
    params = {'access_token':token, 'perpage':perpage, 'page':page}
    api_type = 'serial' if requested_kind in ('series','serial') else ('movie' if requested_kind in ('movies','movie') else '')
    if api_type:
        params['type'] = api_type
    if genre:
        params['genre'] = genre
    if actor_query:
        params['actor'] = actor_query
    elif query:
        params['q'] = query
    else:
        params['sort'] = 'updated-'
    status, data = await _kinopub_api('GET', path, params=params)
    if status == 401:
        return web.json_response({'ok':False,'error':'kinopub_auth_required'}, status=401)
    if status >= 400:
        return web.json_response({'ok':False,'error':'kinopub_catalog_failed','status':status}, status=502)
    rows = []
    for item in _kinopub_extract_items(data):
        row = _kinopub_normalize(item)
        if not row:
            continue
        if requested_kind in ('movies','series') and row['kind'] != requested_kind:
            continue
        rows.append(row)
    total = _kinopub_total_from_data(data)
    if actor_query:
        logging.info('KINOPUB_ACTOR_QUERY actor=%s count=%s total=%s status=%s', actor_query, len(rows), total, status)
    return web.json_response({
        'ok':True,'items':rows,'count':len(rows),'total':total,
        'page':page,'perpage':perpage,
        'has_more':bool(len(rows) > 0 and (total is None or page * perpage < total)),
    }, headers={'Cache-Control':'no-store'})


def _apk_target(channel='stable'):
    channel = 'beta' if str(channel or '').lower() == 'beta' else 'stable'
    if channel == 'beta':
        return APK_BETA_PATH, APK_BETA_META_PATH, PUBLIC_APK_BETA_PATH, channel
    return APK_PATH, APK_META_PATH, PUBLIC_APK_PATH, channel

def _read_apk_meta(channel='stable'):
    _, meta_path, _, _ = _apk_target(channel)
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

async def index(request):
    path = os.path.join(WEB_DIR, 'index.html')
    return web.FileResponse(path, headers={'Cache-Control':'no-store, no-cache, must-revalidate, max-age=0','Pragma':'no-cache'})

async def abaj_site(request):
    return web.FileResponse(os.path.join(WEB_DIR, 'site.html'), headers={'Cache-Control':'no-cache'})

async def favicon(request):
    path = os.path.join(WEB_DIR, 'abaj_tv_logo.svg')
    return web.FileResponse(path, headers={'Cache-Control':'public, max-age=86400'})

async def privacy_policy(request):
    path = os.path.join(WEB_DIR, 'privacy.html')
    return web.FileResponse(path, headers={'Cache-Control':'public, max-age=3600'})

async def api_app_release(request):
    channel = request.query.get('channel') or request.headers.get('X-AbajTV-Channel') or 'stable'
    apk_path, _, public_path, channel = _apk_target(channel)
    meta = _read_apk_meta(channel)
    available = os.path.isfile(apk_path) and os.path.getsize(apk_path) >= MIN_APK_SIZE
    return web.json_response({'ok':True,'service':'abajtv-ota','channel':channel,'available':available,'version_name':str(meta.get('version_name') or ''),'version_code':int(meta.get('version_code') or 0),'size_bytes':os.path.getsize(apk_path) if available else 0,'download_url':public_path if available else '','published_at':meta.get('published_at')}, headers={'Cache-Control':'no-store, max-age=0'})

async def api_app_download(request):
    channel = 'beta' if request.path.endswith('AbajTV-beta.apk') or request.query.get('channel') == 'beta' else 'stable'
    apk_path, _, _, channel = _apk_target(channel)
    if not os.path.isfile(apk_path) or os.path.getsize(apk_path) < MIN_APK_SIZE:
        raise web.HTTPNotFound(text='APK not published yet')
    filename = 'AbajTV-beta.apk' if channel == 'beta' else 'AbajTV-latest.apk'
    return web.FileResponse(
        apk_path,
        headers={
            'Content-Type':'application/vnd.android.package-archive',
            'Content-Disposition':f'attachment; filename="{filename}"',
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
    version_name = (request.headers.get('X-FaceTalk-App-Version') or request.headers.get('X-AbajTV-App-Version') or '').strip() or '1.0.0'
    try: version_code = int(request.headers.get('X-FaceTalk-App-Version-Code') or request.headers.get('X-AbajTV-App-Version-Code') or '0')
    except Exception: version_code = 0
    if version_code <= 0: return web.json_response({'ok':False,'error':'invalid version code'}, status=400)
    channel = request.headers.get('X-AbajTV-Channel') or request.query.get('channel') or 'stable'
    apk_path, meta_path, public_path, channel = _apk_target(channel)
    if channel == 'stable' and os.path.isfile(apk_path) and os.path.getsize(apk_path) >= MIN_APK_SIZE:
        prev = _read_apk_meta('stable')
        prev_code = int(prev.get('version_code') or 0)
        if prev_code > 0:
            import shutil
            shutil.copy2(apk_path, os.path.join(APK_HISTORY_DIR, f'AbajTV-{prev_code}.apk'))
            with open(os.path.join(APK_HISTORY_DIR, f'AbajTV-{prev_code}.json'),'w',encoding='utf-8') as f:
                json.dump(prev,f,ensure_ascii=False)
    tmp = apk_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, apk_path)
    meta={'version_name':version_name,'version_code':version_code,'size_bytes':len(raw),'published_at':int(time.time()),'channel':channel}
    with open(meta_path+'.tmp','w',encoding='utf-8') as f: json.dump(meta,f,ensure_ascii=False)
    os.replace(meta_path+'.tmp', meta_path)
    return web.json_response({'ok':True,'download_url':public_path,**meta})

async def api_admin_app_rollback(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    requested = int(body.get('version_code') or 0)
    candidates = []
    for name in os.listdir(APK_HISTORY_DIR):
        if not name.startswith('AbajTV-') or not name.endswith('.apk'):
            continue
        try:
            code = int(name[len('AbajTV-'):-4])
        except Exception:
            continue
        candidates.append(code)
    if not candidates:
        return web.json_response({'ok':False,'error':'no rollback builds'}, status=404)
    code = requested if requested in candidates else max(candidates)
    src = os.path.join(APK_HISTORY_DIR, f'AbajTV-{code}.apk')
    meta_src = os.path.join(APK_HISTORY_DIR, f'AbajTV-{code}.json')
    if not os.path.isfile(src):
        return web.json_response({'ok':False,'error':'rollback build missing'}, status=404)
    import shutil
    shutil.copy2(src, APK_PATH)
    meta = {}
    try:
        with open(meta_src,'r',encoding='utf-8') as f: meta=json.load(f)
    except Exception:
        meta={'version_name':f'rollback-{code}','version_code':code}
    meta['published_at']=int(time.time())
    meta['rollback']=True
    with open(APK_META_PATH+'.tmp','w',encoding='utf-8') as f: json.dump(meta,f,ensure_ascii=False)
    os.replace(APK_META_PATH+'.tmp', APK_META_PATH)
    return web.json_response({'ok':True,'rolled_back_to':code,**meta})


async def api_admin_app_promote_beta(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    if not os.path.isfile(APK_BETA_PATH) or os.path.getsize(APK_BETA_PATH) < MIN_APK_SIZE:
        return web.json_response({'ok':False,'error':'beta not available'}, status=404)
    beta = _read_apk_meta('beta')
    beta_code = int(beta.get('version_code') or 0)
    if beta_code <= 0:
        return web.json_response({'ok':False,'error':'invalid beta metadata'}, status=400)
    if os.path.isfile(APK_PATH) and os.path.getsize(APK_PATH) >= MIN_APK_SIZE:
        prev = _read_apk_meta('stable')
        prev_code = int(prev.get('version_code') or 0)
        if prev_code > 0:
            import shutil
            shutil.copy2(APK_PATH, os.path.join(APK_HISTORY_DIR, f'AbajTV-{prev_code}.apk'))
            with open(os.path.join(APK_HISTORY_DIR, f'AbajTV-{prev_code}.json'),'w',encoding='utf-8') as f:
                json.dump(prev,f,ensure_ascii=False)
    import shutil
    shutil.copy2(APK_BETA_PATH, APK_PATH)
    meta = dict(beta)
    meta['channel'] = 'stable'
    meta['published_at'] = int(time.time())
    meta['promoted_from'] = 'beta'
    with open(APK_META_PATH+'.tmp','w',encoding='utf-8') as f:
        json.dump(meta,f,ensure_ascii=False)
    os.replace(APK_META_PATH+'.tmp', APK_META_PATH)
    return web.json_response({'ok':True,'promoted_version_code':beta_code,**meta})


_iptv_state_lock = asyncio.Lock()

async def api_iptv_state(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    device_id = str(request.headers.get('X-Abaj-Device-Id') or 'default').strip()[:120] or 'default'
    raw = await get_setting(f'iptv_state:{uid}', '{}')
    try:
        data = json.loads(raw or '{}')
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    ui_map = data.get('ui') if isinstance(data.get('ui'), dict) else {}
    ui = ui_map.get(device_id) if isinstance(ui_map.get(device_id), dict) else {}
    if not ui:
        ui = {'layout': str(data.get('layout') or ''), 'tv_mode': bool(data.get('tv_mode'))}
    return web.json_response({
        'ok': True,
        'user_id': uid,
        'favorites': list(dict.fromkeys(data.get('favorites') or []))[:500],
        'recent': list(dict.fromkeys(data.get('recent') or []))[:30],
        'last_channel': str(data.get('last_channel') or ''),
        'layout': str(ui.get('layout') or ''),
        'tv_mode': bool(ui.get('tv_mode')),
        'updated_at': int(data.get('updated_at') or 0),
    }, headers={'Cache-Control':'no-store'})


async def api_iptv_state_save(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    device_id = str(request.headers.get('X-Abaj-Device-Id') or 'default').strip()[:120] or 'default'
    body = await request.json()
    async with _iptv_state_lock:
        raw = await get_setting(f'iptv_state:{uid}', '{}')
        try:
            previous = json.loads(raw or '{}')
            if not isinstance(previous, dict):
                previous = {}
        except Exception:
            previous = {}
        ui_map = previous.get('ui') if isinstance(previous.get('ui'), dict) else {}
        if 'layout' in body or 'tv_mode' in body:
            ui_map[device_id] = {
                'layout': 'grid' if body.get('layout') == 'grid' else 'list',
                'tv_mode': bool(body.get('tv_mode')),
            }
        favorites = previous.get('favorites') if isinstance(previous.get('favorites'), list) else []
        recent = previous.get('recent') if isinstance(previous.get('recent'), list) else []
        last_channel = str(previous.get('last_channel') or '')[:80]
        fav_op = body.get('favorite_op') if isinstance(body.get('favorite_op'), dict) else None
        if fav_op:
            fid = str(fav_op.get('id') or '').strip()
            enabled = bool(fav_op.get('enabled'))
            if fid:
                favset = set(str(x) for x in favorites if str(x).strip())
                if enabled:
                    favset.add(fid)
                else:
                    favset.discard(fid)
                favorites = list(favset)[:500]
        elif 'favorites' in body:
            favorites = [str(x) for x in (body.get('favorites') or []) if str(x).strip()][:500]
        if 'recent' in body:
            recent = [str(x) for x in (body.get('recent') or []) if str(x).strip()][:30]
        if 'last_channel' in body:
            last_channel = str(body.get('last_channel') or '')[:80]
        state = {
            'favorites': list(dict.fromkeys(favorites)),
            'recent': list(dict.fromkeys(recent)),
            'last_channel': last_channel,
            'ui': ui_map,
            'updated_at': max(int(time.time() * 1000), int(previous.get('updated_at') or 0) + 1),
        }
        await set_setting(f'iptv_state:{uid}', json.dumps(state, ensure_ascii=False, separators=(',', ':')))
    current_ui = ui_map.get(device_id) if isinstance(ui_map.get(device_id), dict) else {}
    return web.json_response({
        'ok': True, 'user_id': uid,
        'layout': str(current_ui.get('layout') or ''),
        'tv_mode': bool(current_ui.get('tv_mode')),
        **state,
    }, headers={'Cache-Control':'no-store'})


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
    pay = await _edem_payment_state(uid)
    is_admin = bool(ADMIN_ID and int(uid) == int(ADMIN_ID))
    active = is_admin or (pay.get('status') == 'paid' and expires_at > now)
    days_left = None if is_admin else (max(0, (expires_at - now + 86399) // 86400) if expires_at else 0)
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
        item['adult'] = bool(iptv._is_adult_channel(item))
        out.append(item)
    _edem_cache[uid] = {'url': playlist_url, 'ts': now, 'channels': out}
    return {'configured': True, 'channels': out, 'playlist_url': playlist_url, **sub}


async def _tv_device_usage(uid: int, current_device_id: str = '') -> tuple[int, bool]:
    rows = await list_settings_prefix('tv_device:')
    count = 0
    current_registered = False
    for row in rows:
        raw = str(row.get('value') or '').strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if int(data.get('user_id') or 0) != int(uid):
            continue
        device_id = str(row.get('key') or '')[len('tv_device:'):]
        count += 1
        if current_device_id and device_id == current_device_id:
            current_registered = True
    return count, current_registered


async def _tv_binding_allowed(request, uid: int) -> bool:
    if str(request.headers.get('X-Abaj-TV') or '') != '1':
        return True
    device_id = (request.headers.get('X-Abaj-Device-Id') or '').strip()[:120]
    if not device_id:
        return False
    raw = await get_setting(f'tv_device:{device_id}', '')
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except Exception:
        return False
    return int(data.get('user_id') or 0) == int(uid)


async def api_iptv_edem_status(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _tv_binding_allowed(request, uid):
        return web.json_response({'ok':False,'error':'tv_disconnected'}, status=403)
    raw = await get_setting(f'edem_playlist:{uid}', '')
    sub = await _edem_subscription_state(uid)
    pay = await _edem_payment_state(uid)
    device_count, _ = await _tv_device_usage(uid)
    device_limit = 0 if (ADMIN_ID and uid == int(ADMIN_ID)) else 3
    return web.json_response({
        'ok': True,
        'configured': bool((raw or '').strip()),
        **sub,
        'payment': pay,
        'device_count': device_count,
        'device_limit': device_limit,
    }, headers={'Cache-Control':'no-store'})


async def api_iptv_edem_channels(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if not await _tv_binding_allowed(request, uid):
        return web.json_response({'ok':False,'error':'tv_disconnected'}, status=403)
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
    if not await _tv_binding_allowed(request, uid):
        return web.json_response({'ok':False,'error':'tv_disconnected'}, status=403)
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


async def api_admin_access_users(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)

    ids = set(await list_user_ids())
    for prefix in ('edem_payment:', 'edem_playlist:', 'edem_expires_at:'):
        for row in await list_settings_prefix(prefix):
            try:
                ids.add(int(str(row.get('key') or '').split(':', 1)[1]))
            except Exception:
                pass

    rows = []
    active_count = 0
    pending_count = 0
    now = int(time.time())
    for uid in sorted(ids):
        is_admin = bool(ADMIN_ID and int(uid) == int(ADMIN_ID))
        if not is_admin and str(await get_setting(f'abaj_access_hidden:{uid}', '0') or '0') == '1':
            continue
        sub = await _edem_subscription_state(uid)
        pay = await _edem_payment_state(uid)
        device_count, _ = await _tv_device_usage(uid)
        if sub['active'] and not is_admin:
            active_count += 1
        if pay.get('status') == 'pending' and not is_admin:
            pending_count += 1
        name = ''
        username = ''
        try:
            chat = await request.app['bot'].get_chat(uid)
            name = str(getattr(chat, 'full_name', '') or getattr(chat, 'first_name', '') or '')
            username = str(getattr(chat, 'username', '') or '')
        except Exception:
            pass
        rows.append({
            'user_id': uid,
            'name': name,
            'username': username,
            'active': bool(sub['active']),
            'expires_at': int(sub.get('expires_at') or 0),
            'days_left': sub.get('days_left'),
            'payment_status': str(pay.get('status') or 'none'),
            'device_count': int(device_count),
            'device_limit': 0 if is_admin else 3,
            'is_admin': is_admin,
        })

    rows.sort(key=lambda x: (not x['is_admin'], not x['active'], x['payment_status'] != 'pending', x['name'] or str(x['user_id'])))
    return web.json_response({
        'ok': True,
        'total': sum(1 for x in rows if not x['is_admin']),
        'active_count': active_count,
        'pending_count': pending_count,
        'users': rows,
        'now': now,
    }, headers={'Cache-Control':'no-store'})


async def api_admin_access_set(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
    except Exception:
        return web.json_response({'ok':False,'error':'bad user_id'}, status=400)
    action = str(body.get('action') or '').strip().lower()
    if action not in {'grant', 'revoke', 'reject', 'delete'}:
        return web.json_response({'ok':False,'error':'bad action'}, status=400)
    now = int(time.time())
    if action == 'grant':
        await set_setting(f'abaj_access_hidden:{uid}', '0')
        expires_at = now + 365 * 86400
        await set_setting(f'edem_expires_at:{uid}', str(expires_at))
        pay = {'status':'paid','last_paid_at':now,'plan_days':365,'last_amount':0}
        await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
        try:
            await request.app['bot'].send_message(uid, '✅ Доступ к Abaj TV активирован администратором на 12 месяцев.')
        except Exception:
            pass
    elif action == 'reject':
        await set_setting(f'edem_expires_at:{uid}', '0')
        pay = await _edem_payment_state(uid)
        pay['status'] = 'rejected'
        await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
        _edem_sessions.pop(uid, None)
        try:
            await request.app['bot'].send_message(uid, '❌ Запрос на доступ к Abaj TV отклонён администратором.')
        except Exception:
            pass
    elif action == 'delete':
        await set_setting(f'edem_expires_at:{uid}', '0')
        await set_setting(f'edem_playlist:{uid}', '')
        pay = await _edem_payment_state(uid)
        pay['status'] = 'deleted'
        await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
        await set_setting(f'abaj_access_hidden:{uid}', '1')
        _edem_sessions.pop(uid, None)
    else:
        await set_setting(f'edem_expires_at:{uid}', '0')
        pay = await _edem_payment_state(uid)
        pay['status'] = 'revoked'
        await set_setting(f'edem_payment:{uid}', json.dumps(pay, ensure_ascii=False, separators=(',', ':')))
        _edem_sessions.pop(uid, None)
        try:
            await request.app['bot'].send_message(uid, '⛔ Доступ к Abaj TV отключён администратором.')
        except Exception:
            pass
    sub = await _edem_subscription_state(uid)
    return web.json_response({'ok':True,'user_id':uid,**sub})


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


async def api_iptv_edem_payment_request(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    if ADMIN_ID and uid == int(ADMIN_ID):
        await set_setting(f'edem_payment:{uid}', json.dumps({'status':'admin','last_paid_at':0,'plan_days':0,'last_amount':0}, separators=(',', ':')))
        return web.json_response({'ok':True,'admin':True,'payment_required':False})
    body = await request.json()
    try:
        plan_days = max(365, min(3650, int(body.get('plan_days') or 365)))
        amount = max(12.0, float(body.get('amount') or 12))
    except Exception:
        return web.json_response({'ok':False,'error':'bad values'}, status=400)

    payment = {
        'status':'pending',
        'requested_at':int(time.time()),
        'last_paid_at':0,
        'plan_days':plan_days,
        'last_amount':amount,
    }
    await set_setting(f'abaj_access_hidden:{uid}', '0')
    await set_setting(f'edem_payment:{uid}', json.dumps(payment, ensure_ascii=False, separators=(',', ':')))

    try:
        if ADMIN_ID:
            name = str(user.get('first_name') or user.get('username') or uid)
            username = ('@' + str(user.get('username'))) if user.get('username') else ''
            await request.app['bot'].send_message(
                ADMIN_ID,
                '💳 Abaj TV: пользователь нажал «Оплатил»\n'
                f'Пользователь: {name} {username}\n'
                f'Telegram ID: {uid}\n'
                f'Тариф: {plan_days} дней · {amount:g} USDT · TRC20',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='✅ Получил', callback_data=f'payment:received:{uid}')
                ]])
            )
    except Exception as e:
        print('payment admin notify failed', repr(e))

    return web.json_response({'ok':True,'payment':payment})


async def api_cinema_catalog_cache(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    kind = "series" if str((body or {}).get("type") or "").lower() == "series" else "movies"
    rows = (body or {}).get("items") or []
    if not isinstance(rows, list):
        return web.json_response({"ok": False, "error": "bad_items"}, status=400)
    clean = []
    for row in rows[:120]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        clean.append({
            "id": str(row.get("id") or row.get("data_id") or row.get("intent") or title)[:500],
            "title": title[:240],
            "poster": str(row.get("poster") or "")[:2000],
            "year": str(row.get("year") or "")[:20],
            "quality": str(row.get("quality") or "")[:40],
            "height": int(row.get("height") or 0) if str(row.get("height") or "").isdigit() else 0,
            "url": str(row.get("url") or "")[:4000],
            "intent": str(row.get("intent") or "")[:2000],
            "source": "lazy",
        })
    await set_setting(f"cinema_catalog:{kind}", json.dumps(clean, ensure_ascii=False, separators=(",", ":")))
    await set_setting(f"cinema_catalog_updated:{kind}", str(int(time.time())))
    return web.json_response({"ok": True, "count": len(clean), "type": kind}, headers={"Cache-Control": "no-store"})



def _imdb_clean_image(url):
    url = str(url or "").strip()
    if not url:
        return ""
    return re.sub(r"_V1_[^./]+(?=\.(?:jpg|jpeg|png|webp)(?:\?|$))", "_V1_", url, flags=re.I)

def _imdb_name(value):
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, list):
        return ", ".join([_imdb_name(x) for x in value if _imdb_name(x)])
    return str(value or "").strip()

def _cinema_translit(value):
    table = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
        'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
        'х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    }
    out = []
    for ch in str(value or '').casefold():
        out.append(table.get(ch, ch))
    return ''.join(out)

def _cinema_norm(value):
    value = _cinema_translit(value)
    return re.sub(r'[^a-z0-9]+', '', value)

def _cinema_title_score(query, candidate):
    q = _cinema_norm(query)
    c = _cinema_norm(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    if q in c or c in q:
        return 72
    import difflib
    return int(difflib.SequenceMatcher(None, q, c).ratio() * 60)

async def _wiki_person_lookup(name, session):
    try:
        host = 'ru.wikipedia.org' if re.search(r'[А-Яа-яЁё]', str(name or '')) else 'en.wikipedia.org'
        params = {
            'action':'query','generator':'search','gsrsearch':str(name or ''),'gsrlimit':'3',
            'prop':'pageimages|langlinks|pageprops','piprop':'thumbnail','pithumbsize':'500',
            'lllang':'en','lllimit':'1','format':'json'
        }
        async with session.get('https://' + host + '/w/api.php', params=params, allow_redirects=True) as resp:
            data = await resp.json(content_type=None) if resp.status < 400 else {}
        pages = ((data or {}).get('query') or {}).get('pages') or {}
        rows = list(pages.values()) if isinstance(pages, dict) else []
        if not rows:
            return {}
        target = str(name or '').lower()
        rows.sort(key=lambda row: _cinema_title_score(target, str(row.get('title') or '').lower()), reverse=True)
        best = rows[0]
        thumb = best.get('thumbnail') if isinstance(best, dict) else {}
        image = str((thumb or {}).get('source') or '').strip() if isinstance(thumb, dict) else ''
        en_name = ''
        links = best.get('langlinks') if isinstance(best, dict) else []
        if isinstance(links, list) and links:
            en_name = str((links[0] or {}).get('*') or '').strip()
        return {'name':str(best.get('title') or name),'english_name':en_name,'image':image}
    except Exception:
        return {}

async def api_cinema_verified_cast_photo(request):
    """Fetch portraits via exact Wikidata sitelinks, never approximate search hits."""
    name = str(request.query.get('name') or '').strip()
    if not (2 <= len(name) <= 100):
        return web.json_response({'ok':False,'image':''}, status=400)
    image = ''
    def norm(v):
        return re.sub(r'[^\w]+', ' ', str(v or '').casefold(), flags=re.UNICODE).strip()
    try:
        timeout = aiohttp.ClientTimeout(total=10, connect=4, sock_read=6)
        headers = {'User-Agent':'AbajTV/1.0 (verified cast portrait)', 'Accept':'application/json'}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            # Query the exact Wikipedia page in both languages; redirects may
            # resolve alternate names, but fuzzy search results are never trusted.
            for host in ('ru.wikipedia.org','en.wikipedia.org'):
                params = {'action':'query','titles':name,'redirects':'1',
                          'prop':'pageimages|langlinks|pageprops','piprop':'thumbnail',
                          'pithumbsize':'500','lllang':'en','format':'json'}
                try:
                    async with session.get('https://'+host+'/w/api.php',params=params) as resp:
                        data=await resp.json(content_type=None) if resp.status<400 else {}
                    query=data.get('query') if isinstance(data,dict) else {}
                    redirects=query.get('redirects') or []
                    aliases=[name]+[str(x.get('to') or '') for x in redirects if isinstance(x,dict)]
                    for page in (query.get('pages') or {}).values():
                        if not isinstance(page,dict) or page.get('missing') is not None:
                            continue
                        title=str(page.get('title') or '')
                        # Allow a documented redirect from the exact requested name.
                        if norm(title) not in {norm(x) for x in aliases}:
                            continue
                        thumb=page.get('thumbnail') or {}
                        url=str(thumb.get('source') or '').strip()
                        if url.startswith('https://'):
                            image=url
                            break
                        # The exact biography page may have no thumbnail even
                        # when Wikidata provides its linked portrait (P18).
                        entity_id=str((page.get('pageprops') or {}).get('wikibase_item') or '')
                        if re.fullmatch(r'Q[1-9][0-9]*',entity_id):
                            try:
                                wd_url='https://www.wikidata.org/wiki/Special:EntityData/'+entity_id+'.json'
                                async with session.get(wd_url) as wd_resp:
                                    wd=await wd_resp.json(content_type=None) if wd_resp.status<400 else {}
                                claims=((wd.get('entities') or {}).get(entity_id) or {}).get('claims') or {}
                                for claim in claims.get('P18') or []:
                                    filename=str((((claim.get('mainsnak') or {}).get('datavalue') or {}).get('value') or '')).strip()
                                    if filename and '/' not in filename and len(filename)<200:
                                        image='https://commons.wikimedia.org/wiki/Special:FilePath/'+quote(filename)+'?width=500'
                                        break
                            except Exception:
                                pass
                        if image:
                            break
                    if image:
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return web.json_response({'ok':True,'image':image},
                             headers={'Cache-Control':'public, max-age=21600'})

async def api_cinema_person(request):
    name = str(request.query.get('name') or '').strip()
    if len(name) < 2 or len(name) > 100:
        return web.json_response({'ok':False,'error':'invalid_name'}, status=400)
    timeout = aiohttp.ClientTimeout(total=8, connect=4, sock_read=5)
    headers = {'Accept':'application/json,*/*','User-Agent':'Mozilla/5.0 AbajTV'}
    try:
        url = 'https://v2.sg.media-imdb.com/suggestion/x/' + quote(name) + '.json'
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                data = await resp.json(content_type=None) if resp.status < 400 else {}
        rows = data.get('d') if isinstance(data, dict) else []
        best = None
        best_score = -1
        for pos,row in enumerate(rows if isinstance(rows,list) else []):
            if not isinstance(row,dict):
                continue
            imdb_id = str(row.get('id') or '')
            if not imdb_id.startswith('nm'):
                continue
            label = str(row.get('l') or row.get('name') or '').strip()
            score = _cinema_title_score(name,label) + max(0,30-pos*3)
            if score > best_score:
                best_score = score
                best = row
        if not best:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as wiki_session:
                wiki = await _wiki_person_lookup(name, wiki_session)
            if wiki:
                return web.json_response({'ok':True,'found':bool(wiki.get('image')),'name':wiki.get('english_name') or wiki.get('name') or name,'image':wiki.get('image') or ''}, headers={'Cache-Control':'public, max-age=86400'})
            return web.json_response({'ok':True,'found':False}, headers={'Cache-Control':'public, max-age=21600'})
        image = ''
        i = best.get('i')
        if isinstance(i,dict):
            image = str(i.get('imageUrl') or i.get('url') or '').strip()
        return web.json_response({'ok':True,'found':bool(image),'name':str(best.get('l') or name),'image':_imdb_clean_image(image)}, headers={'Cache-Control':'public, max-age=86400'})
    except Exception:
        return web.json_response({'ok':True,'found':False}, headers={'Cache-Control':'public, max-age=1800'})

async def api_cinema_person_photo(request):
    name = str(request.query.get('name') or '').strip()
    if len(name) < 2 or len(name) > 100:
        raise web.HTTPNotFound()
    timeout = aiohttp.ClientTimeout(total=10, connect=4, sock_read=6)
    headers = {'Accept':'application/json,image/*,*/*','User-Agent':'Mozilla/5.0 AbajTV'}
    try:
        suggest_url = 'https://v2.sg.media-imdb.com/suggestion/x/' + quote(name) + '.json'
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(suggest_url, allow_redirects=True) as resp:
                data = await resp.json(content_type=None) if resp.status < 400 else {}
            rows = data.get('d') if isinstance(data, dict) else []
            best = None
            best_score = -1
            for pos,row in enumerate(rows if isinstance(rows,list) else []):
                if not isinstance(row,dict) or not str(row.get('id') or '').startswith('nm'):
                    continue
                label = str(row.get('l') or row.get('name') or '').strip()
                score = _cinema_title_score(name,label) + max(0,30-pos*3)
                if score > best_score:
                    best_score = score
                    best = row
            image = ''
            if not best:
                wiki = await _wiki_person_lookup(name, session)
                image = str(wiki.get('image') or '').strip() if isinstance(wiki, dict) else ''
                if not image:
                    raise web.HTTPNotFound()
            else:
                i = best.get('i')
                if isinstance(i,dict):
                    image = str(i.get('imageUrl') or i.get('url') or '').strip()
            image = _imdb_clean_image(image)
            if not image:
                raise web.HTTPNotFound()
            async with session.get(image, allow_redirects=True) as img:
                if img.status >= 400:
                    raise web.HTTPNotFound()
                body = await img.read()
                ctype = str(img.headers.get('Content-Type') or 'image/jpeg')
        return web.Response(body=body, content_type=ctype.split(';')[0], headers={'Cache-Control':'public, max-age=86400'})
    except web.HTTPException:
        raise
    except Exception:
        raise web.HTTPNotFound()

async def api_cinema_meta(request):
    title = str(request.query.get("title") or "").strip()
    year_raw = str(request.query.get("year") or "").strip()
    exact_imdb_id = str(request.query.get("imdb_id") or "").strip()
    if exact_imdb_id and not re.fullmatch(r"tt\d+", exact_imdb_id, re.I):
        return web.json_response({"ok":False,"error":"invalid_imdb_id"}, status=400)
    if not title and not exact_imdb_id:
        return web.json_response({"ok":False,"error":"title_required"}, status=400)
    try:
        wanted_year = int(year_raw) if year_raw.isdigit() else 0
    except Exception:
        wanted_year = 0

    timeout = aiohttp.ClientTimeout(total=12, connect=5, sock_read=8)
    headers = {
        "Accept":"application/json,text/html;q=0.9,*/*;q=0.8",
        "User-Agent":"Mozilla/5.0 (Linux; Android TV 11) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7",
    }
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            best = None
            best_score = -1

            if exact_imdb_id:
                best = {"id": exact_imdb_id, "l": title, "y": year_raw}
                best_score = 1000

            if not best:
                try:
                    suggest_url = "https://v2.sg.media-imdb.com/suggestion/x/" + quote(title) + ".json"
                    async with session.get(suggest_url, allow_redirects=True) as resp:
                        data = await resp.json(content_type=None) if resp.status < 400 else {}
                    candidates = data.get("d") if isinstance(data, dict) else []
                    for pos, row in enumerate(candidates if isinstance(candidates, list) else []):
                        if not isinstance(row, dict):
                            continue
                        imdb_id = str(row.get("id") or "")
                        if not imdb_id.startswith("tt"):
                            continue
                        row_year = int(row.get("y") or 0) if str(row.get("y") or "").isdigit() else 0
                        if wanted_year and row_year and abs(wanted_year-row_year) > 1:
                            continue
                        score = max(0, 90 - pos * 12)
                        score += _cinema_title_score(title, row.get("l") or "") // 4
                        if wanted_year and row_year == wanted_year:
                            score += 55
                        elif wanted_year and row_year:
                            score += 20
                        if score > best_score:
                            best_score = score
                            best = row
                except Exception:
                    pass

            if not best:
                for meta_type in ("movie","series"):
                    try:
                        search_url = (
                            f"https://v3-cinemeta.strem.io/catalog/{meta_type}/top/search="
                            + quote(title)
                            + ".json"
                        )
                        async with session.get(search_url, allow_redirects=True) as resp:
                            if resp.status >= 400:
                                continue
                            search_data = await resp.json(content_type=None)
                        metas = search_data.get("metas") if isinstance(search_data, dict) else []
                        for pos, row in enumerate(metas if isinstance(metas, list) else []):
                            if not isinstance(row, dict):
                                continue
                            imdb_id = str(row.get("imdb_id") or row.get("id") or "")
                            if not imdb_id.startswith("tt"):
                                continue
                            row_year_raw = str(row.get("year") or row.get("releaseInfo") or "")
                            year_match = re.search(r"(19|20)\d{2}", row_year_raw)
                            row_year = int(year_match.group(0)) if year_match else 0
                            if wanted_year and row_year and abs(wanted_year-row_year) > 1:
                                continue
                            score = _cinema_title_score(title, row.get("name") or "")
                            score += max(0, 35 - pos * 5)
                            if wanted_year and row_year == wanted_year:
                                score += 45
                            if score > best_score:
                                best_score = score
                                best = {
                                    "id": imdb_id,
                                    "l": row.get("name") or "",
                                    "y": row_year or "",
                                    "_cinemeta_search": row,
                                }
                    except Exception:
                        continue

            if not best:
                return web.json_response({"ok":True,"found":False}, headers={"Cache-Control":"no-store"})

            imdb_id = str(best.get("id") or "")
            page_url = f"https://www.imdb.com/title/{imdb_id}/"
            async with session.get(page_url, allow_redirects=True) as resp:
                page = await resp.text(errors="ignore")
                if resp.status >= 400:
                    page = ""

            cinemeta = {}
            for meta_type in ("movie","series"):
                try:
                    meta_url = f"https://v3-cinemeta.strem.io/meta/{meta_type}/{imdb_id}.json"
                    async with session.get(meta_url, allow_redirects=True) as resp:
                        if resp.status >= 400:
                            continue
                        cm = await resp.json(content_type=None)
                        if isinstance(cm, dict) and isinstance(cm.get("meta"), dict):
                            cinemeta = cm["meta"]
                            if cinemeta.get("name"):
                                break
                except Exception:
                    continue

        ld = {}
        if page:
            m = re.search(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                page, re.I|re.S
            )
            if m:
                try:
                    parsed = json.loads(html.unescape(m.group(1)).strip())
                    if isinstance(parsed, dict):
                        ld = parsed
                except Exception:
                    ld = {}

        aggregate = ld.get("aggregateRating") if isinstance(ld.get("aggregateRating"), dict) else {}
        trailer = ld.get("trailer") if isinstance(ld.get("trailer"), dict) else {}
        cinemeta_trailer = ""
        if isinstance(cinemeta, dict):
            raw_trailer = cinemeta.get("trailer")
            if isinstance(raw_trailer, str) and raw_trailer.strip():
                cinemeta_trailer = raw_trailer.strip()
            if not cinemeta_trailer:
                trailers = cinemeta.get("trailers")
                if isinstance(trailers, list):
                    preferred = []
                    for row in trailers:
                        if not isinstance(row, dict):
                            continue
                        source = str(row.get("source") or row.get("id") or row.get("youtubeId") or "").strip()
                        if not source:
                            continue
                        kind = str(row.get("type") or row.get("name") or "").lower()
                        preferred.append((0 if "trailer" in kind else 1, source))
                    if preferred:
                        preferred.sort(key=lambda x:x[0])
                        cinemeta_trailer = preferred[0][1]
            if cinemeta_trailer and re.fullmatch(r"[A-Za-z0-9_-]{6,}", cinemeta_trailer):
                cinemeta_trailer = "https://www.youtube.com/watch?v=" + cinemeta_trailer
        duration = str(ld.get("duration") or "")
        if duration.startswith("PT"):
            h = re.search(r"(\d+)H", duration)
            mn = re.search(r"(\d+)M", duration)
            total = (int(h.group(1))*60 if h else 0) + (int(mn.group(1)) if mn else 0)
            duration = f"{total} мин." if total else duration

        genres = ld.get("genre")
        if isinstance(genres, list):
            genres = ", ".join(str(x) for x in genres if x)
        elif not isinstance(genres, str):
            genres = ""

        actors = _imdb_name(ld.get("actor"))
        directors = _imdb_name(ld.get("director"))
        image = _imdb_clean_image(ld.get("image") or (best.get("i") or {}).get("imageUrl") if isinstance(best.get("i"), dict) else "")

        cm_genres = cinemeta.get("genres") if isinstance(cinemeta, dict) else []
        if isinstance(cm_genres, list):
            cm_genres = ", ".join(str(x) for x in cm_genres if x)
        cm_director = cinemeta.get("director") if isinstance(cinemeta, dict) else []
        cm_cast = cinemeta.get("cast") if isinstance(cinemeta, dict) else []
        result = {
            "ok":True,
            "found":True,
            "imdb_id":imdb_id,
            "title":str((cinemeta or {}).get("name") or ld.get("name") or best.get("l") or title),
            "original_title":str(ld.get("alternateName") or ""),
            "year":str((cinemeta or {}).get("year") or best.get("y") or year_raw or ""),
            "description":str((cinemeta or {}).get("description") or ld.get("description") or ""),
            "rating":str((cinemeta or {}).get("imdbRating") or aggregate.get("ratingValue") or ""),
            "duration":str((cinemeta or {}).get("runtime") or duration or ""),
            "genre":str(cm_genres or genres or ""),
            "director":_imdb_name(cm_director) or directors,
            "actors":_imdb_name(cm_cast) or actors,
            "country":str((cinemeta or {}).get("country") or _imdb_name(ld.get("countryOfOrigin")) or ""),
            "poster":str((cinemeta or {}).get("poster") or image or ""),
            "backdrop":str((cinemeta or {}).get("background") or ""),
            "trailer":str(cinemeta_trailer or trailer.get("embedUrl") or trailer.get("url") or ""),
        }
        return web.json_response(result, headers={"Cache-Control":"public, max-age=21600"})
    except Exception as exc:
        return web.json_response(
            {"ok":False,"error":"metadata_unavailable","detail":str(exc)[:160]},
            status=502,
            headers={"Cache-Control":"no-store"},
        )


async def api_cinema_search(request):
    q = str(request.query.get("q") or "").strip().casefold()
    if not q:
        return web.json_response({"ok": True, "items": []}, headers={"Cache-Control": "no-store"})
    merged = []
    seen = set()
    for kind in ("movies", "series"):
        raw = await get_setting(f"cinema_catalog:{kind}", "[]")
        try:
            rows = json.loads(raw or "[]")
        except Exception:
            rows = []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join([
                str(row.get("title") or ""),
                str(row.get("year") or ""),
                str(row.get("source") or ""),
            ]).casefold()
            if q not in text:
                continue
            key = str(row.get("intent") or row.get("id") or row.get("title") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            item = dict(row)
            item["kind"] = kind
            merged.append(item)
            if len(merged) >= 100:
                break
        if len(merged) >= 100:
            break
    return web.json_response({"ok": True, "items": merged}, headers={"Cache-Control": "no-store"})


async def api_admin_cinema_playback_provider(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    if request.method == "GET":
        endpoint = str(await get_setting("cinema_playback_endpoint", "") or "").strip()
        auth_mode = str(await get_setting("cinema_playback_auth_mode", "none") or "none").strip()
        username = str(await get_setting("cinema_playback_username", "") or "").strip()
        token = str(await get_setting("cinema_playback_token", "") or "").strip()
        password = str(await get_setting("cinema_playback_password", "") or "").strip()
        return web.json_response({
            "ok": True,
            "endpoint": endpoint,
            "auth_mode": auth_mode,
            "username": username,
            "has_token": bool(token),
            "has_password": bool(password),
            "configured": bool(endpoint),
        }, headers={"Cache-Control": "no-store"})

    body = await request.json()
    endpoint = str(body.get("endpoint") or "").strip()[:2000]
    auth_mode = str(body.get("auth_mode") or "none").strip().lower()
    username = str(body.get("username") or "").strip()[:240]
    if auth_mode not in ("none", "bearer", "basic"):
        auth_mode = "none"
    if endpoint:
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return web.json_response({"ok": False, "error": "invalid_endpoint"}, status=400)
    await set_setting("cinema_playback_endpoint", endpoint)
    await set_setting("cinema_playback_auth_mode", auth_mode)
    await set_setting("cinema_playback_username", username)
    if "token" in body:
        await set_setting("cinema_playback_token", str(body.get("token") or "")[:1000])
    if "password" in body:
        await set_setting("cinema_playback_password", str(body.get("password") or "")[:1000])
    return web.json_response({"ok": True, "configured": bool(endpoint)}, headers={"Cache-Control": "no-store"})


async def api_cinema_resolve(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    uid = int(user['id'])
    if not await _cinema_playback_allowed(uid):
        return web.json_response({"ok": False, "error": "subscription_required"}, status=403)

    body = await request.json()
    endpoint = str(await get_setting("cinema_playback_endpoint", "") or "").strip()
    if not endpoint:
        return web.json_response({"ok": False, "error": "provider_not_configured"}, status=503)

    payload = {
        "title": str(body.get("title") or "")[:240],
        "year": str(body.get("year") or "")[:20],
        "type": "series" if str(body.get("type") or "").lower() == "series" else "movie",
        "provider_id": str(body.get("id") or "")[:1000],
        "source": str(body.get("source") or "")[:120],
        "article": str(body.get("intent") or "")[:3000],
    }

    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "AbajTV/1.0"}
    auth = None
    auth_mode = str(await get_setting("cinema_playback_auth_mode", "none") or "none").strip().lower()
    if auth_mode == "bearer":
        token = str(await get_setting("cinema_playback_token", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_mode == "basic":
        username = str(await get_setting("cinema_playback_username", "") or "").strip()
        password = str(await get_setting("cinema_playback_password", "") or "").strip()
        auth = aiohttp.BasicAuth(username, password)

    timeout = aiohttp.ClientTimeout(total=18, connect=7, sock_read=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, auth=auth) as session:
            async with session.post(endpoint, json=payload, allow_redirects=True) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    return web.json_response({"ok": False, "error": f"provider_http_{resp.status}"}, status=502)
    except Exception as exc:
        return web.json_response({"ok": False, "error": "provider_unavailable", "detail": str(exc)[:180]}, status=502)

    if not isinstance(data, dict):
        return web.json_response({"ok": False, "error": "bad_provider_response"}, status=502)

    url = str(data.get("url") or data.get("stream_url") or data.get("play_url") or "").strip()
    parsed = urlparse(url) if url else None
    if not url or not parsed or parsed.scheme not in ("http", "https"):
        return web.json_response({"ok": False, "error": "no_stream"}, status=404)

    return web.json_response({
        "ok": True,
        "url": url,
        "quality": str(data.get("quality") or ""),
        "headers": data.get("headers") if isinstance(data.get("headers"), dict) else {},
    }, headers={"Cache-Control": "no-store"})


async def api_support_message(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    if not ADMIN_ID:
        return web.json_response({'ok':False,'error':'admin_unavailable'}, status=503)
    body = await request.json()
    text = str(body.get('text') or '').strip()
    if not text:
        return web.json_response({'ok':False,'error':'empty'}, status=400)
    if len(text) > 1500:
        text = text[:1500]
    uid = int(user['id'])
    name = str(user.get('first_name') or user.get('username') or uid)
    username = ('@' + str(user.get('username'))) if user.get('username') else ''
    try:
        sent = await request.app['bot'].send_message(
            ADMIN_ID,
            '💬 Abaj TV · сообщение администратору\n'
            f'Пользователь: {name} {username}\n'
            f'Telegram ID: {uid}\n\n'
            f'{text}\n\n'
            '↩️ Ответьте на это сообщение — ответ уйдёт пользователю.'
        )
        await set_setting(f'support_admin_msg:{int(sent.message_id)}', str(uid))
        await set_setting(f'support_last_user:{uid}', str(int(sent.message_id)))
    except Exception as e:
        print('support admin notify failed', repr(e))
        return web.json_response({'ok':False,'error':'send_failed'}, status=502)
    return web.json_response({'ok':True})


async def api_admin_iptv_edem_payment(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    try:
        uid = int(body.get('user_id'))
        plan_days = max(365, min(3650, int(body.get('plan_days') or 365)))
        amount = max(12.0, float(body.get('amount') or 12))
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


def _tv_pair_sign(uid: int, ts: int) -> str:
    import hmac, hashlib
    return hmac.new(TELEGRAM_BOT_TOKEN.encode(), f"{int(uid)}:{int(ts)}".encode(), hashlib.sha256).hexdigest()


async def api_tv_pair_start(request):
    import secrets
    body = await request.json()
    device_id = str(body.get('device_id') or request.headers.get('X-Abaj-Device-Id') or '').strip()[:120]
    device_secret = str(body.get('device_secret') or '').strip()[:180]
    device_name = str(body.get('device_name') or '').strip()[:120]
    app_version = str(body.get('app_version') or '').strip()[:40]
    try: app_version_code = max(0, int(body.get('app_version_code') or 0))
    except Exception: app_version_code = 0
    if not device_id or not device_secret:
        return web.json_response({'ok':False,'error':'device_required'}, status=400)

    # If this TV was paired before, refresh auth immediately without asking again.
    saved = await get_setting(f'tv_device:{device_id}', '')
    if saved:
        try:
            data = json.loads(saved)
        except Exception:
            data = {}
        if data.get('secret') == device_secret and int(data.get('user_id') or 0) > 0:
            uid = int(data['user_id'])
            now = int(time.time())
            data['last_seen'] = now
            if device_name: data['device_name'] = device_name
            if app_version: data['app_version'] = app_version
            if app_version_code: data['app_version_code'] = app_version_code
            await set_setting(f'tv_device:{device_id}', json.dumps(data, separators=(',',':')))
            ts = now
            return web.json_response({
                'ok':True,'paired':True,'user_id':uid,
                'ft_uid':str(uid),'ft_ts':str(ts),'ft_sig':_tv_pair_sign(uid, ts),
            }, headers={'Cache-Control':'no-store'})

    # Create a short human-readable pairing code.
    for _ in range(12):
        code = f"{secrets.randbelow(1000000):06d}"
        existing = await get_setting(f'tv_pair:{code}', '')
        if not existing:
            break
    else:
        return web.json_response({'ok':False,'error':'pair_code_unavailable'}, status=503)

    expires_at = int(time.time()) + 600
    payload = {
        'device_id':device_id,
        'device_secret':device_secret,
        'device_name':device_name,
        'app_version':app_version,
        'app_version_code':app_version_code,
        'created_at':int(time.time()),
        'expires_at':expires_at,
        'user_id':0,
    }
    await set_setting(f'tv_pair:{code}', json.dumps(payload, separators=(',',':')))
    me = await request.app['bot'].get_me()
    username = (me.username or '').lstrip('@')
    deeplink = f'https://t.me/{username}?start=tv_{code}' if username else ''
    return web.json_response({
        'ok':True,'paired':False,'code':code,'expires_at':expires_at,'deeplink':deeplink,
    }, headers={'Cache-Control':'no-store'})


async def api_tv_pair_open(request):
    code = str(request.query.get('code') or '').strip()
    if len(code) != 6 or not code.isdigit():
        raise web.HTTPBadRequest(text='Invalid TV code')
    raw = await get_setting(f'tv_pair:{code}', '')
    if not raw:
        raise web.HTTPNotFound(text='TV code not found')
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if int(data.get('expires_at') or 0) < int(time.time()):
        raise web.HTTPGone(text='TV code expired')
    me = await request.app['bot'].get_me()
    username = (me.username or '').lstrip('@')
    if not username:
        raise web.HTTPServiceUnavailable(text='Telegram bot unavailable')
    tg_url = f'tg://resolve?domain={username}&start=tv_{code}'
    web_url = f'https://t.me/{username}?start=tv_{code}'
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Abaj TV</title><style>
body{{font-family:Arial,sans-serif;background:#eef7ff;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;color:#123}}
.card{{width:min(460px,90vw);background:#fff;border-radius:24px;padding:26px;text-align:center;box-shadow:0 12px 40px #1253a522}}
h1{{color:#087fe1}} .code{{font-size:42px;font-weight:900;letter-spacing:7px;margin:18px 0}}
a{{display:block;text-decoration:none;border-radius:14px;padding:15px;margin:10px 0;font-weight:800}}
.primary{{background:#087fe1;color:#fff}} .secondary{{background:#e7f3ff;color:#087fe1}}
.small{{color:#657b8d;font-size:14px;line-height:1.4}}
</style></head><body><div class="card">
<h1>Подключить Abaj TV</h1><div class="code">{code}</div>
<a class="primary" href="{tg_url}">Открыть Telegram и подключить</a>
<a class="secondary" href="{web_url}">Открыть через t.me</a>
<div class="small">Если Telegram откроет только профиль бота, откройте чат и отправьте код <b>{code}</b> обычным сообщением.</div>
</div><script>
window.location.href={json.dumps(tg_url)};
setTimeout(function(){{ window.location.href={json.dumps(web_url)}; }},900);
</script></body></html>"""
    return web.Response(text=page, content_type='text/html', headers={'Cache-Control':'no-store, max-age=0'})


async def api_tv_pair_qr(request):
    import io
    import qrcode
    import qrcode.image.svg
    code = str(request.query.get('code') or '').strip()
    if len(code) != 6 or not code.isdigit():
        return web.json_response({'ok':False,'error':'bad_code'}, status=400)
    raw = await get_setting(f'tv_pair:{code}', '')
    if not raw:
        return web.json_response({'ok':False,'error':'not_found'}, status=404)
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if int(data.get('expires_at') or 0) < int(time.time()):
        return web.json_response({'ok':False,'error':'expired'}, status=410)
    me = await request.app['bot'].get_me()
    username = (me.username or '').lstrip('@')
    if not username:
        return web.json_response({'ok':False,'error':'bot_unavailable'}, status=503)
    # Use a tiny redirect page in the QR so Android scanners first try the
    # native Telegram scheme (opens the bot chat with START), then fall back
    # to the normal t.me deep link if the scheme is not handled.
    landing = f'{request.scheme}://{request.host}/api/tv/pair/open?code={code}'
    img = qrcode.make(landing, image_factory=qrcode.image.svg.SvgPathImage, border=2, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    return web.Response(
        body=buf.getvalue(),
        content_type='image/svg+xml',
        headers={'Cache-Control':'no-store, max-age=0','X-Content-Type-Options':'nosniff'},
    )


_tv_pair_lock = asyncio.Lock()


async def api_tv_pair_status(request):
    code = str(request.query.get('code') or '').strip()
    device_id = str(request.query.get('device_id') or request.headers.get('X-Abaj-Device-Id') or '').strip()[:120]
    device_secret = str(request.query.get('device_secret') or '').strip()[:180]
    if len(code) != 6 or not code.isdigit() or not device_id or not device_secret:
        return web.json_response({'ok':False,'error':'bad_request'}, status=400)
    raw = await get_setting(f'tv_pair:{code}', '')
    if not raw:
        return web.json_response({'ok':False,'error':'not_found'}, status=404)
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if data.get('device_id') != device_id or data.get('device_secret') != device_secret:
        return web.json_response({'ok':False,'error':'mismatch'}, status=403)
    if int(data.get('expires_at') or 0) < int(time.time()):
        return web.json_response({'ok':False,'error':'expired'}, status=410)
    uid = int(data.get('user_id') or 0)
    if uid <= 0:
        return web.json_response({'ok':True,'paired':False,'expires_at':int(data.get('expires_at') or 0)}, headers={'Cache-Control':'no-store'})

    async with _tv_pair_lock:
        if not (ADMIN_ID and uid == int(ADMIN_ID)):
            device_count, already_registered = await _tv_device_usage(uid, device_id)
            if not already_registered and device_count >= 3:
                return web.json_response({
                    'ok':False,'paired':False,'error':'device_limit','limit':3,'active':device_count
                }, status=409, headers={'Cache-Control':'no-store'})

        await set_setting(f'tv_device:{device_id}', json.dumps({
            'secret':device_secret,'user_id':uid,'device_name':str(data.get('device_name') or '')[:120],
            'app_version':str(data.get('app_version') or '')[:40],
            'app_version_code':int(data.get('app_version_code') or 0),
            'paired_at':int(time.time()),'last_seen':int(time.time())
        }, separators=(',',':')))
    ts = int(time.time())
    return web.json_response({
        'ok':True,'paired':True,'user_id':uid,
        'ft_uid':str(uid),'ft_ts':str(ts),'ft_sig':_tv_pair_sign(uid, ts),
    }, headers={'Cache-Control':'no-store'})


async def api_tv_device_auth(request):
    body = await request.json()
    device_id = str(body.get('device_id') or request.headers.get('X-Abaj-Device-Id') or '').strip()[:120]
    device_secret = str(body.get('device_secret') or '').strip()[:180]
    device_name = str(body.get('device_name') or '').strip()[:120]
    app_version = str(body.get('app_version') or '').strip()[:40]
    try: app_version_code = max(0, int(body.get('app_version_code') or 0))
    except Exception: app_version_code = 0
    current_channel_id = str(body.get('current_channel_id') or '').strip()[:120]
    current_channel_name = str(body.get('current_channel_name') or '').strip()[:160]
    if not device_id or not device_secret:
        return web.json_response({'ok':False,'error':'device_required'}, status=400)
    raw = await get_setting(f'tv_device:{device_id}', '')
    if not raw:
        signed_user = await _user_from_request(request)
        if signed_user:
            uid = int(signed_user['id'])
            if ADMIN_ID and uid == int(ADMIN_ID):
                can_restore = True
            else:
                device_count, already_registered = await _tv_device_usage(uid, device_id)
                can_restore = already_registered or device_count < 3
            if can_restore:
                now = int(time.time())
                data = {
                    'secret':device_secret,
                    'user_id':uid,
                    'device_name':device_name,
                    'app_version':app_version,
                    'app_version_code':app_version_code,
                    'paired_at':now,
                    'last_seen':now,
                    'current_channel_id':current_channel_id,
                    'current_channel_name':current_channel_name,
                }
                await set_setting(f'tv_device:{device_id}', json.dumps(data, separators=(',',':')))
                return web.json_response({
                    'ok':True,'paired':True,'user_id':uid,
                    'ft_uid':str(uid),'ft_ts':str(now),'ft_sig':_tv_pair_sign(uid, now),
                    'restored':True,
                }, headers={'Cache-Control':'no-store'})
        return web.json_response({'ok':True,'paired':False}, headers={'Cache-Control':'no-store'})
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if data.get('secret') != device_secret:
        return web.json_response({'ok':False,'error':'mismatch'}, status=403)
    uid = int(data.get('user_id') or 0)
    if uid <= 0:
        return web.json_response({'ok':True,'paired':False}, headers={'Cache-Control':'no-store'})
    now = int(time.time())
    data['last_seen'] = now
    if device_name: data['device_name'] = device_name
    if app_version: data['app_version'] = app_version
    if app_version_code: data['app_version_code'] = app_version_code
    previous_channel = str(data.get('current_channel_id') or '')
    if current_channel_id and current_channel_id != previous_channel:
        data['channel_switches'] = int(data.get('channel_switches') or 0) + 1
    data['current_channel_id'] = current_channel_id
    data['current_channel_name'] = current_channel_name
    if current_channel_id:
        try:
            free_item = iptv._state.get('channels', {}).get(current_channel_id)
            if free_item and free_item.get('status') == 'ONLINE':
                iptv._burned_ad_stats['last_free_play'] = now
                iptv._burned_ad_stats['last_free_play_channel_id'] = current_channel_id
        except Exception:
            pass
    await set_setting(f'tv_device:{device_id}', json.dumps(data, separators=(',',':')))
    ts = now
    return web.json_response({
        'ok':True,'paired':True,'user_id':uid,
        'ft_uid':str(uid),'ft_ts':str(ts),'ft_sig':_tv_pair_sign(uid, ts),
    }, headers={'Cache-Control':'no-store'})


async def api_tv_devices(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    current_device_id = str(request.headers.get('X-Abaj-Device-Id') or '').strip()[:120]
    rows = await list_settings_prefix('tv_device:')
    devices = []
    now = int(time.time())
    for row in rows:
        raw = str(row.get('value') or '').strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if int(data.get('user_id') or 0) != uid:
            continue
        device_id = str(row.get('key') or '')[len('tv_device:'):]
        last_seen = int(data.get('last_seen') or 0)
        devices.append({
            'device_id': device_id,
            'device_name': str(data.get('device_name') or 'Android TV')[:120],
            'paired_at': int(data.get('paired_at') or 0),
            'last_seen': last_seen,
            'online': bool(last_seen and now - last_seen <= 10 * 60),
            'current': bool(current_device_id and device_id == current_device_id),
            'app_version': str(data.get('app_version') or '')[:40],
        })
    devices.sort(key=lambda x: (not x.get('current'), -(x.get('last_seen') or x.get('paired_at') or 0)))
    limit = 0 if (ADMIN_ID and uid == int(ADMIN_ID)) else 3
    return web.json_response({'ok':True,'devices':devices,'limit':limit}, headers={'Cache-Control':'no-store'})


async def api_tv_disconnect(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    body = await request.json()
    device_id = str(body.get('device_id') or '').strip()[:120]
    if not device_id:
        return web.json_response({'ok':False,'error':'device_required'}, status=400)
    raw = await get_setting(f'tv_device:{device_id}', '')
    if not raw:
        return web.json_response({'ok':True,'removed':False}, headers={'Cache-Control':'no-store'})
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if int(data.get('user_id') or 0) != uid:
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    await set_setting(f'tv_device:{device_id}', '')
    sessions = _edem_sessions.get(uid) or {}
    sessions.pop(device_id, None)
    return web.json_response({'ok':True,'removed':True,'device_id':device_id}, headers={'Cache-Control':'no-store'})


async def api_admin_tv_devices(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    rows = await list_settings_prefix('tv_device:')
    devices = []
    for row in rows:
        raw = str(row.get('value') or '').strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        uid = int(data.get('user_id') or 0)
        if uid <= 0:
            continue
        device_id = str(row.get('key') or '')[len('tv_device:'):]
        active = device_id in _edem_prune_sessions(uid)
        last_seen = int(data.get('last_seen') or 0)
        devices.append({
            'device_id': device_id,
            'device_name': str(data.get('device_name') or 'Android TV')[:120],
            'user_id': uid,
            'paired_at': int(data.get('paired_at') or 0),
            'last_seen': last_seen,
            'online': bool(last_seen and int(time.time()) - last_seen <= 10 * 60),
            'app_version': str(data.get('app_version') or '')[:40],
            'app_version_code': int(data.get('app_version_code') or 0),
            'current_channel_id': str(data.get('current_channel_id') or '')[:120],
            'current_channel_name': str(data.get('current_channel_name') or '')[:160],
            'channel_switches': int(data.get('channel_switches') or 0),
            'stream_active': bool(active),
        })
    devices.sort(key=lambda x: x.get('last_seen') or x.get('paired_at') or 0, reverse=True)
    return web.json_response({'ok':True,'devices':devices}, headers={'Cache-Control':'no-store'})


async def api_admin_tv_disconnect(request):
    user = await _user_from_request(request)
    if not user or not _is_admin_user(user):
        return web.json_response({'ok':False,'error':'forbidden'}, status=403)
    body = await request.json()
    device_id = str(body.get('device_id') or '').strip()[:120]
    if not device_id:
        return web.json_response({'ok':False,'error':'bad device_id'}, status=400)
    raw = await get_setting(f'tv_device:{device_id}', '')
    uid = 0
    if raw:
        try:
            uid = int(json.loads(raw).get('user_id') or 0)
        except Exception:
            uid = 0
    await set_setting(f'tv_device:{device_id}', '')
    if uid > 0:
        _edem_sessions.setdefault(uid, {}).pop(device_id, None)
    return web.json_response({'ok':True,'device_id':device_id,'user_id':uid})


async def api_app_auth_start(request):
    me = await request.app['bot'].get_me()
    username = (me.username or '').lstrip('@')
    if not username: raise web.HTTPServiceUnavailable(text='Telegram bot username unavailable')
    nonce = ''.join(ch for ch in (request.query.get('nonce') or '') if ch.isalnum() or ch in ('-','_'))[:96]
    payload = f'app_login_{nonce}' if nonce else 'app_login'
    raise web.HTTPFound(f'https://t.me/{quote(username)}?start={quote(payload)}')

async def api_app_auth_status(request):
    nonce = ''.join(ch for ch in (request.query.get('nonce') or '') if ch.isalnum() or ch in ('-','_'))[:96]
    if not nonce:
        return web.json_response({'ok':False,'paired':False}, status=400)
    raw = await get_setting(f'app_login_nonce:{nonce}')
    if not raw:
        return web.json_response({'ok':True,'paired':False})
    try:
        data = json.loads(raw)
        uid = int(data.get('user_id') or 0)
        created = int(data.get('created_at') or 0)
    except Exception:
        return web.json_response({'ok':True,'paired':False})
    if uid <= 0 or created <= 0 or int(time.time()) - created > 900:
        return web.json_response({'ok':True,'paired':False})
    ts = int(time.time())
    sig = hmac.new(TELEGRAM_BOT_TOKEN.encode(), f'{uid}:{ts}'.encode(), hashlib.sha256).hexdigest()
    return web.json_response({'ok':True,'paired':True,'ft_uid':str(uid),'ft_ts':str(ts),'ft_sig':sig})

async def api_app_auth_complete(request):
    init_data = (request.query.get('init_data') or '').strip()
    user = validate_init_data(init_data, max_age=7*86400)
    if not user: raise web.HTTPForbidden(text='Invalid or expired Telegram login')
    uid = int(user['id'])
    ts = int(time.time())
    sig = hmac.new(TELEGRAM_BOT_TOKEN.encode(), f'{uid}:{ts}'.encode(), hashlib.sha256).hexdigest()
    raise web.HTTPFound('facetalk://auth?' + urlencode({
        'init_data': init_data,
        'ft_uid': str(uid),
        'ft_ts': str(ts),
        'ft_sig': sig,
    }))

_ai_dub_locks = {}
_ai_dub_context = {}

async def api_iptv_ai_dub_chunk(request):
    user = await _user_from_request(request)
    if not user:
        return web.json_response({'ok':False,'error':'unauthorized'}, status=401)
    uid = int(user['id'])
    try:
        body = await request.json()
    except Exception:
        body = {}
    cid = str(body.get('channel_id') or '').strip()
    lang = str(body.get('lang') or '').strip().lower()
    if lang not in {'ru','hy','en'}:
        return web.json_response({'ok':False,'error':'bad language'}, status=400)
    item = iptv._state.get('channels', {}).get(cid)
    if not item or item.get('status') != 'ONLINE':
        return web.json_response({'ok':False,'error':'channel unavailable'}, status=404)

    candidates = []
    for source in [str(item.get('url') or ''), *[str(x or '') for x in (item.get('backups') or [])]]:
        source = source.strip()
        if source and source not in candidates:
            candidates.append(source)
    if not candidates:
        return web.json_response({'ok':False,'error':'stream unavailable'}, status=404)

    lock = _ai_dub_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return web.json_response({'ok':False,'error':'busy'}, status=429)

    async with lock:
        import tempfile
        wav_path = ''
        tts_path = ''
        selected_source = ''
        try:
            fd, wav_path = tempfile.mkstemp(prefix='abaj-ai-dub-', suffix='.wav', dir=DATA_DIR)
            os.close(fd)

            capture_error = ''
            for source in candidates[:3]:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        'ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                        '-user_agent','IPTV-Player/1.0',
                        '-rw_timeout','7000000',
                        '-reconnect','1','-reconnect_streamed','1','-reconnect_delay_max','1',
                        '-i',source,
                        '-vn','-t','6.8','-ac','1','-ar','16000','-af','highpass=f=90,lowpass=f=7600',
                        '-y',wav_path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        _, err = await asyncio.wait_for(proc.communicate(), timeout=16)
                    except asyncio.TimeoutError:
                        proc.kill()
                        _, err = await proc.communicate()
                    if proc.returncode == 0 and os.path.isfile(wav_path) and os.path.getsize(wav_path) >= 1800:
                        selected_source = source
                        break
                    capture_error = (err or b'').decode('utf-8','ignore')[-260:]
                except Exception as exc:
                    capture_error = str(exc)[:260]

            if not selected_source:
                return web.json_response({'ok':False,'error':'audio unavailable','detail':capture_error[:160]}, status=422)

            text, stt_provider = await ai_service.transcribe_dub(wav_path)
            text = (text or '').strip()
            if len(text) < 2:
                return web.Response(status=204)

            previous = _ai_dub_context.get(uid) or {}
            if previous.get('channel_id') != cid or previous.get('lang') != lang:
                previous = {}
            context = str(previous.get('source_text') or '')[-1400:]
            translated = (await ai_service.translate_text(text, lang, context=context)).strip()
            if not translated:
                return web.Response(status=204)

            _ai_dub_context[uid] = {
                'channel_id': cid,
                'lang': lang,
                'source_text': (context + '\n' + text).strip()[-2200:],
                'updated_at': int(time.time()),
            }

            tts_path, tts_provider = await ai_service.synthesize_dub(translated, lang)
            if not tts_path or not os.path.isfile(tts_path):
                return web.json_response({'ok':False,'error':'voice unavailable'}, status=503)
            with open(tts_path,'rb') as audio_file:
                audio = audio_file.read()
            if not audio:
                return web.Response(status=204)
            return web.Response(
                body=audio,
                content_type='audio/mpeg',
                headers={
                    'Cache-Control':'no-store',
                    'X-Abaj-AI-Lang':lang,
                    'X-Abaj-AI-STT':str(stt_provider)[:80],
                    'X-Abaj-AI-TTS':str(tts_provider)[:80],
                    'X-Abaj-AI-Text-Len':str(len(text)),
                    'X-Abaj-AI-Translation-Len':str(len(translated)),
                },
            )
        except Exception as exc:
            return web.json_response({'ok':False,'error':str(exc)[:180]}, status=503)
        finally:
            for path in (wav_path, tts_path):
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass


async def api_healthz(request):
    channels_loaded = bool(iptv._state.get("channels"))
    payload = {
        "ok": channels_loaded,
        "service": "abaj-tv",
        "channels_loaded": channels_loaded,
        "last_refresh": int(iptv._state.get("last_refresh") or 0),
    }
    return web.json_response(
        payload,
        status=200 if channels_loaded else 503,
        headers={"Cache-Control":"no-store"},
    )


async def start_webapp(bot):
    app = web.Application(client_max_size=100*1024*1024, middlewares=[api_error_middleware]); app['bot']=bot
    app.router.add_get('/', index)
    app.router.add_get('/site', abaj_site)
    app.router.add_get('/site/', abaj_site)
    app.router.add_get('/favicon.ico', favicon)
    app.router.add_get('/healthz', api_healthz)
    app.router.add_get('/privacy', privacy_policy)
    app.router.add_get('/privacy-policy', privacy_policy)
    iptv.install(app)
    app.router.add_get('/api/app-release', api_app_release); app.router.add_get('/api/app-download', api_app_download); app.router.add_get(PUBLIC_APK_PATH, api_app_download); app.router.add_get(PUBLIC_APK_BETA_PATH, api_app_download); app.router.add_get('/downloads/FaceTalkAI-latest.apk', api_app_download); app.router.add_post('/api/app-upload', api_app_upload)
    app.router.add_get('/api/admin/app-release', api_app_release); app.router.add_get('/api/admin/app-download', api_app_download); app.router.add_post('/api/admin/app-upload', api_app_upload); app.router.add_post('/api/admin/app-rollback', api_admin_app_rollback); app.router.add_post('/api/admin/app-promote-beta', api_admin_app_promote_beta)
    app.router.add_get('/api/app-auth/telegram-start', api_app_auth_start); app.router.add_get('/api/app-auth/status', api_app_auth_status); app.router.add_get('/api/app-auth/complete', api_app_auth_complete)
    app.router.add_post('/api/tv/pair/start', api_tv_pair_start); app.router.add_get('/api/tv/pair/status', api_tv_pair_status); app.router.add_get('/api/tv/pair/open', api_tv_pair_open); app.router.add_get('/api/tv/pair/qr', api_tv_pair_qr); app.router.add_post('/api/tv/device-auth', api_tv_device_auth)
    app.router.add_get('/api/tv/devices', api_tv_devices); app.router.add_post('/api/tv/disconnect', api_tv_disconnect)
    app.router.add_get('/api/cinema/source-state', api_cinema_source_state); app.router.add_post('/api/admin/cinema/source-state', api_admin_cinema_source_state)
    app.router.add_get('/api/kinopub/status', api_kinopub_status); app.router.add_post('/api/kinopub/auth/start', api_kinopub_auth_start); app.router.add_post('/api/kinopub/auth/poll', api_kinopub_auth_poll); app.router.add_post('/api/kinopub/disconnect', api_kinopub_disconnect); app.router.add_get('/api/kinopub/catalog', api_kinopub_catalog); app.router.add_get('/api/kinopub/play', api_kinopub_play); app.router.add_get('/api/kinopub/benchmark', api_kinopub_benchmark); app.router.add_get('/api/kinopub/proxy', api_kinopub_proxy); app.router.add_get('/api/kinopub/download', api_kinopub_download); app.router.add_get('/api/kinopub/item', api_kinopub_item)
    app.router.add_get('/api/kinopub/overview', api_kinopub_overview); app.router.add_get('/api/cinema/rating', api_cinema_rating); app.router.add_post('/api/cinema/rating', api_cinema_rating); app.router.add_get('/api/cinema/library', api_cinema_library); app.router.add_get('/api/cinema/bookmark-folders', api_cinema_bookmark_folders); app.router.add_post('/api/cinema/bookmark-folders', api_cinema_bookmark_folders); app.router.add_post('/api/cinema/library/bookmark', api_cinema_library_bookmark); app.router.add_post('/api/cinema/library/watch', api_cinema_library_watch); app.router.add_get('/api/kinopub/filters', api_kinopub_filters); app.router.add_get('/api/kinopub/section', api_kinopub_section); app.router.add_get('/api/kinopub/collection', api_kinopub_collection_items); app.router.add_get('/api/cinema/progress', api_cinema_progress); app.router.add_post('/api/cinema/progress', api_cinema_progress)
    app.router.add_get('/api/admin/tv/devices', api_admin_tv_devices); app.router.add_post('/api/admin/tv/disconnect', api_admin_tv_disconnect)
    app.router.add_get('/api/iptv/state', api_iptv_state); app.router.add_post('/api/iptv/state', api_iptv_state_save)
    app.router.add_get('/api/iptv/edem/status', api_iptv_edem_status); app.router.add_get('/api/iptv/edem/channels', api_iptv_edem_channels); app.router.add_get('/api/iptv/edem/play', api_iptv_edem_play); app.router.add_get('/api/iptv/edem/proxy', api_iptv_edem_proxy); app.router.add_post('/api/iptv/edem/payment-request', api_iptv_edem_payment_request)
    app.router.add_post('/api/iptv/ai-dub/chunk', api_iptv_ai_dub_chunk)
    app.router.add_post('/api/cinema/catalog-cache', api_cinema_catalog_cache)
    app.router.add_get('/api/cinema/search', api_cinema_search)
    app.router.add_get('/api/cinema/person', api_cinema_person)
    app.router.add_get('/api/cinema/verified-cast-photo', api_cinema_verified_cast_photo); app.router.add_get('/api/cinema/person-photo', api_cinema_person_photo); app.router.add_get('/api/cinema/meta', api_cinema_meta)
    app.router.add_post('/api/cinema/resolve', api_cinema_resolve)
    app.router.add_get('/api/admin/cinema/playback-provider', api_admin_cinema_playback_provider); app.router.add_post('/api/admin/cinema/playback-provider', api_admin_cinema_playback_provider)
    app.router.add_post('/api/support/message', api_support_message)
    app.router.add_get('/api/admin/iptv/edem', api_admin_iptv_edem_list); app.router.add_post('/api/admin/iptv/edem/assign', api_admin_iptv_edem_assign); app.router.add_post('/api/admin/iptv/edem/limit', api_admin_iptv_edem_limit); app.router.add_post('/api/admin/iptv/edem/subscription', api_admin_iptv_edem_subscription); app.router.add_post('/api/admin/iptv/edem/payment', api_admin_iptv_edem_payment); app.router.add_get('/api/admin/access/users', api_admin_access_users); app.router.add_post('/api/admin/access/set', api_admin_access_set)
    app.router.add_get('/api/me', api_me); app.router.add_get('/api/admin/stats', api_admin_stats); app.router.add_get('/api/admin/keys', api_admin_keys); app.router.add_post('/api/admin/keys', api_admin_keys)
    app.router.add_get('/api/admin/gpu-health', api_admin_gpu_health); app.router.add_post('/api/admin/video-limit', api_admin_video_limit)
    app.router.add_get('/api/photo', api_photo); app.router.add_get('/api/profile-photo', api_profile_photo); app.router.add_post('/api/role', api_role); app.router.add_post('/api/mode', api_mode); app.router.add_post('/api/reset', api_reset)
    app.router.add_post('/api/upload-photo', api_upload_photo); app.router.add_post('/api/voice-clone', api_voice_clone); app.router.add_post('/api/voice-clone/delete', api_delete_voice_clone); app.router.add_post('/api/profile/select', api_profile_select); app.router.add_post('/api/profile/rename', api_profile_rename); app.router.add_post('/api/chat', api_chat)
    app.router.add_static('/generated/', GEN_DIR, show_index=False); app.router.add_static('/static/', WEB_DIR, show_index=False)
    runner=web.AppRunner(app); await runner.setup(); site=web.TCPSite(runner,'0.0.0.0',PORT); await site.start()
    print('IPTV Player web endpoints active')
    app['cleanup_task']=__import__('asyncio').create_task(cleanup_generated(app)); return runner
