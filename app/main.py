import asyncio
import os
import logging
import hashlib
import hmac
import json
import time
from io import BytesIO
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import qrcode

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, BufferedInputFile

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_TOKEN_SOURCE, MINIAPP_URL, DATA_DIR, DB_PATH, EXPECTED_BOT_USERNAME, ADMIN_ID
from .db import init_db, set_user_language, get_user_language, get_setting, set_setting, list_settings_prefix
from .webapp_plus import start_webapp
from .storage import migrate_legacy_db

logging.basicConfig(level=logging.INFO)
BUILD_VERSION = 'abaj-tv-v1'

bot = None
dp = Dispatcher()

async def _track_message(chat_id: int, message_id: int):
    if not bot:
        return
    key = f'chat_recent_messages:{int(chat_id)}'
    raw = await get_setting(key, '[]')
    try:
        ids = [int(x) for x in json.loads(raw or '[]') if int(x) > 0]
    except Exception:
        ids = []
    if message_id not in ids:
        ids.append(int(message_id))
    stale = ids[:-3]
    ids = ids[-3:]
    await set_setting(key, json.dumps(ids, separators=(',', ':')))
    for old_id in stale:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_id)
        except Exception:
            pass

async def _track_incoming(m: Message):
    if m.chat:
        await _track_message(m.chat.id, m.message_id)

async def _answer(m: Message, *args, **kwargs):
    sent = await m.answer(*args, **kwargs)
    await _track_message(sent.chat.id, sent.message_id)
    return sent

async def _answer_photo(m: Message, *args, **kwargs):
    sent = await m.answer_photo(*args, **kwargs)
    await _track_message(sent.chat.id, sent.message_id)
    return sent

async def _hide_reply_keyboard(m: Message):
    try:
        sent = await m.answer('·', reply_markup=ReplyKeyboardRemove())
        await bot.delete_message(chat_id=sent.chat.id, message_id=sent.message_id)
    except Exception:
        pass

def _apk_download_url():
    if not MINIAPP_URL:
        return ""
    parts = urlsplit(MINIAPP_URL)
    return urlunsplit((parts.scheme, parts.netloc, "/downloads/AbajTV-latest.apk", "", ""))

def _tv_apk_download_url():
    return "https://github.com/edgar198282-ux/FaceTalkAi/releases/download/abajtv-tv-compat/AbajTV-TV-compat.apk"

async def _bot_start_link(payload: str = "") -> str:
    username = EXPECTED_BOT_USERNAME.strip().lstrip('@') if EXPECTED_BOT_USERNAME else ''
    if not username and bot:
        try:
            me = await bot.get_me()
            username = str(getattr(me, 'username', '') or '').strip().lstrip('@')
        except Exception:
            username = ''
    if not username:
        return ''
    return f"https://t.me/{username}?start={payload}" if payload else f"https://t.me/{username}"

async def _tv_apk_qr_photo() -> tuple[BufferedInputFile | None, str]:
    link = await _bot_start_link('tv_apk')
    if not link:
        return None, ''
    image = qrcode.make(link)
    buf = BytesIO()
    image.save(buf, format='PNG')
    return BufferedInputFile(buf.getvalue(), filename='AbajTV-TV-QR.png'), link

def start_keyboard(user_id: int | None = None, lang: str = "ru"):
    rows = []
    if MINIAPP_URL:
        rows.append([InlineKeyboardButton(
            text={"hy":"📺 Բացել Abaj TV","ru":"📺 Открыть Abaj TV","en":"📺 Open Abaj TV"}.get(lang, "📺 Открыть Abaj TV"),
            web_app=WebAppInfo(url=_miniapp_url_for_user(user_id))
        )])
    apk_url = _apk_download_url()
    tv_apk_url = _tv_apk_download_url()
    if apk_url:
        rows.append([
            InlineKeyboardButton(
                text={"hy":"📱 Հեռախոս APK","ru":"📱 Телефон APK","en":"📱 Phone APK"}.get(lang, "📱 Телефон APK"),
                url=apk_url
            ),
            InlineKeyboardButton(
                text={"hy":"📺 Android TV APK","ru":"📺 Android TV APK","en":"📺 Android TV APK"}.get(lang, "📺 Android TV APK"),
                url=tv_apk_url
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🇦🇲 Հայերեն", callback_data="lang:hy"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _miniapp_url_for_user(user_id: int | None):
    if not MINIAPP_URL or not user_id:
        return MINIAPP_URL
    ts = int(time.time())
    payload = f"{int(user_id)}:{ts}"
    sig = hmac.new(TELEGRAM_BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    parts = urlsplit(MINIAPP_URL)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update({'ft_uid': str(int(user_id)), 'ft_ts': str(ts), 'ft_sig': sig})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

def _telegram_init_data_for_user(user) -> str:
    now = int(time.time())
    user_payload = {
        'id': int(user.id),
        'first_name': user.first_name or 'IPTV User',
        'last_name': user.last_name or '',
        'username': user.username or '',
        'language_code': user.language_code or '',
        'allows_write_to_pm': True,
    }
    payload = {
        'auth_date': str(now),
        'query_id': f'apk-{user.id}-{now}',
        'user': json.dumps(user_payload, ensure_ascii=False, separators=(',', ':')),
    }
    check = '\n'.join(f'{k}={payload[k]}' for k in sorted(payload))
    secret = hmac.new(b'WebAppData', TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    payload['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)

def miniapp_keyboard(user_id: int | None = None, lang: str = 'ru'):
    if not MINIAPP_URL:
        return None
    labels={'hy':'📺 Բացել Abaj TV','ru':'📺 Открыть Abaj TV','en':'📺 Open Abaj TV'}
    apk_labels={'hy':'📱 Ներբեռնել APK','ru':'📱 Скачать APK','en':'📱 Download APK'}
    tv_apk_labels={'hy':'🖥️ Ներբեռնել TV APK','ru':'🖥️ Скачать TV APK','en':'🖥️ Download TV APK'}
    qr_labels={'hy':'📷 QR TV-ի համար','ru':'📷 QR для TV','en':'📷 QR for TV'}
    share_labels={'hy':'📤 Կիսվել','ru':'📤 Поделиться','en':'📤 Share'}
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=labels.get(lang, labels['ru']), web_app=WebAppInfo(url=_miniapp_url_for_user(user_id)))],
                  [KeyboardButton(text=apk_labels.get(lang, apk_labels['ru']))],
                  [KeyboardButton(text=tv_apk_labels.get(lang, tv_apk_labels['ru']))],
                  [KeyboardButton(text=qr_labels.get(lang, qr_labels['ru']))],
                  [KeyboardButton(text=share_labels.get(lang, share_labels['ru']))]],
        resize_keyboard=True,
        is_persistent=True,
    )

async def _ensure_latest_menu(m: Message, lang: str):
    if not m.from_user:
        return
    key = f'menu_version:{int(m.from_user.id)}'
    if await get_setting(key, '') == 'share-v3':
        return
    await _answer(
        m,
        {'hy':'Թարմացված մենյու 👇','ru':'Обновлённое меню 👇','en':'Updated menu 👇'}.get(lang, 'Обновлённое меню 👇'),
        reply_markup=miniapp_keyboard(m.from_user.id, lang),
    )
    await set_setting(key, 'share-v3')

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🇦🇲 Հայերեն', callback_data='lang:hy')],
        [InlineKeyboardButton(text='🇷🇺 Русский', callback_data='lang:ru')],
        [InlineKeyboardButton(text='🇬🇧 English', callback_data='lang:en')],
    ])

TEXTS={
 'hy':('📺 Abaj TV','3000+ ալիքներ։ Գինը՝ ընդամենը 1 USDT ամսական։ Նվազագույն վճարումը՝ 12 ամիս = 12 USDT։ Աշխատում է ցանկացած Android TV-ում։ Վճարումից հետո կարող եք միացնել մինչև 3 սարք։\n\nՎճարումից հետո սեղմեք «✅ Վճարել եմ»։ Ադմինիստրատորը կստուգի վճարումը և կսեղմի «Ստացել եմ», դրանից հետո ալիքները կբացվեն։ Մինչ հաստատումը ալիքների ցանկը դատարկ կլինի։'),
 'ru':('📺 Abaj TV','Более 3000 каналов. Цена — всего 1 USDT в месяц. Минимальная оплата — 12 месяцев = 12 USDT. Работает на любом Android TV. После оплаты можно подключить до 3 устройств.\n\nПосле оплаты нажмите «✅ Оплатил». Администратор проверит перевод и нажмёт «Получил», после этого каналы откроются. До подтверждения список каналов будет пустым.'),
 'en':('📺 Abaj TV','3000+ channels. Price: only 1 USDT per month. Minimum payment: 12 months = 12 USDT. Works on any Android TV. After payment, you can connect up to 3 devices.\n\nAfter payment, tap “✅ Paid”. The administrator will verify the transfer and confirm receipt, then the channels will unlock. Until approval, the channel list stays empty.'),
}

PAYMENT_TEXT={
 'hy':'💳 <b>Վճարում՝ USDT TRC20</b>\n\n<code>TG9ZpZAax6uSoWi62CZMKuqE3N9yTD8rJ2</code>',
 'ru':'💳 <b>Оплата: USDT TRC20</b>\n\n<code>TG9ZpZAax6uSoWi62CZMKuqE3N9yTD8rJ2</code>',
 'en':'💳 <b>Payment: USDT TRC20</b>\n\n<code>TG9ZpZAax6uSoWi62CZMKuqE3N9yTD8rJ2</code>',
}

PAY_BUTTON={
 'hy':'✅ Վճարել եմ',
 'ru':'✅ Оплатил',
 'en':'✅ Paid',
}

NO_MINIAPP_TEXT = {
    'hy': 'Abaj TV Mini App-ը դեռ կարգավորված չէ։',
    'ru': 'Abaj TV Mini App ещё не настроен.',
    'en': 'Abaj TV Mini App is not configured yet.',
}

APP_LOGIN_TEXT = {
    'hy': 'Հաստատեք մուտքը Abaj TV։',
    'ru': 'Подтвердите вход в Abaj TV.',
    'en': 'Confirm sign-in to Abaj TV.',
}

APP_LOGIN_BUTTON = {
    'hy': '✅ Բացել Abaj TV',
    'ru': '✅ Открыть Abaj TV',
    'en': '✅ Open Abaj TV',
}


def _telegram_lang(user) -> str:
    code = str(getattr(user, 'language_code', '') or '').lower()
    if code.startswith('hy'):
        return 'hy'
    if code.startswith('en'):
        return 'en'
    return 'ru'

async def send_language_picker(m: Message):
    await _hide_reply_keyboard(m)
    caption = '🌐 Ընտրեք լեզուն / Выберите язык / Choose language'
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media', 'abaj_tv_logo.jpg')
    keyboard = language_keyboard()
    try:
        if os.path.exists(logo_path):
            await _answer_photo(m, FSInputFile(logo_path), caption=caption, reply_markup=keyboard)
            return
    except Exception as exc:
        logging.warning("Abaj TV start photo failed, fallback to text: %r", exc)
    await _answer(m, caption, reply_markup=keyboard)

async def _paired_device_count(uid: int, current_device_id: str = '') -> tuple[int, bool]:
    rows = await list_settings_prefix('tv_device:')
    count = 0
    current_registered = False
    for row in rows:
        try:
            data = json.loads(str(row.get('value') or '') or '{}')
        except Exception:
            continue
        if int(data.get('user_id') or 0) != int(uid):
            continue
        device_id = str(row.get('key') or '')[len('tv_device:'):]
        count += 1
        if current_device_id and device_id == current_device_id:
            current_registered = True
    return count, current_registered


async def _confirm_tv_pair_code(m: Message, code: str, lang: str) -> bool:
    code = str(code or '').strip()
    if len(code) != 6 or not code.isdigit() or not m.from_user:
        return False
    raw = await get_setting(f'tv_pair:{code}', '')
    try:
        data = json.loads(raw or '{}')
    except Exception:
        data = {}
    now = int(time.time())
    if raw and int(data.get('expires_at') or 0) >= now and not int(data.get('user_id') or 0):
        uid = int(m.from_user.id)
        device_id = str(data.get('device_id') or '')[:120]
        if not (ADMIN_ID and uid == int(ADMIN_ID)):
            count, already_registered = await _paired_device_count(uid, device_id)
            if not already_registered and count >= 3:
                await _answer(m, {
                    'hy':'⚠️ Ձեր Abaj TV հաշվում արդեն միացված է առավելագույնը՝ 3 սարք։ Անջատեք հին սարքը և կրկին փորձեք։',
                    'ru':'⚠️ К вашему Abaj TV уже подключено максимум 3 устройства. Отключите старое устройство и попробуйте снова.',
                    'en':'⚠️ Your Abaj TV account already has the maximum of 3 devices. Disconnect an old device and try again.'
                }.get(lang,'⚠️ Уже подключено максимум 3 устройства.'))
                return True
        data['user_id'] = uid
        data['paired_at'] = now
        await set_setting(f'tv_pair:{code}', json.dumps(data, separators=(',',':')))
        await _answer(m, {'hy':'✅ Հեռուստացույցը միացված է Abaj TV-ին։','ru':'✅ Телевизор подключён к вашему Abaj TV.','en':'✅ TV connected to your Abaj TV account.'}.get(lang,'✅ Телевизор подключён к вашему Abaj TV.'))
        logging.info('Abaj TV TV pairing confirmed: code=%s user_id=%s device_id=%s', code, m.from_user.id, data.get('device_id'))
        return True
    await _answer(m, {'hy':'Կոդը ժամկետանց է կամ անվավեր։ Ստացեք նոր կոդ հեռուստացույցում։','ru':'Код истёк или недействителен. Получите новый код на телевизоре.','en':'The code expired or is invalid. Get a new code on the TV.'}.get(lang,'Код истёк или недействителен.'))
    logging.warning('Abaj TV TV pairing rejected: code=%s user_id=%s', code, m.from_user.id)
    return True


@dp.message(CommandStart())
async def start_handler(m: Message):
    await _track_incoming(m)
    lang = await get_user_language(m.from_user.id if m.from_user else 0) or _telegram_lang(m.from_user)
    payload = ''
    if m.text:
        parts = m.text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ''

    if payload.startswith('app_login') and MINIAPP_URL:
        if payload.startswith('app_login_'):
            nonce = payload[len('app_login_'):].strip()[:96]
            if nonce and m.from_user:
                await set_setting(f'app_login_nonce:{nonce}', json.dumps({
                    'user_id': int(m.from_user.id),
                    'created_at': int(time.time()),
                }, separators=(',', ':')))
                await _answer(m, '✅ Abaj TV подключён. Вернитесь в приложение.')
                return
        init_data = _telegram_init_data_for_user(m.from_user)
        complete = MINIAPP_URL.rstrip('/') + '/api/app-auth/complete?' + urlencode({'init_data': init_data})
        await _answer(
            m,
            APP_LOGIN_TEXT.get(lang, APP_LOGIN_TEXT['ru']),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=APP_LOGIN_BUTTON.get(lang, APP_LOGIN_BUTTON['ru']), url=complete)
            ]]),
        )
        return

    if payload == 'tv_apk':
        tv_apk_url = _tv_apk_download_url()
        await _answer(
            m,
            {'hy':'📺 Abaj TV Android TV APK','ru':'📺 Abaj TV для Android TV','en':'📺 Abaj TV for Android TV'}.get(lang, '📺 Abaj TV для Android TV'),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text={'hy':'⬇️ Ներբեռնել TV APK','ru':'⬇️ Скачать TV APK','en':'⬇️ Download TV APK'}.get(lang, '⬇️ Скачать TV APK'),
                    url=tv_apk_url,
                )
            ]]),
        )
        return

    if payload.startswith('tv_'):
        code = payload[3:].strip()
        if await _confirm_tv_pair_code(m, code, lang):
            return

    try:
        await send_language_picker(m)
    except Exception as exc:
        logging.exception("Abaj TV /start failed: %r", exc)
        await _answer(m, '🌐 Ընտրեք լեզուն / Выберите язык / Choose language', reply_markup=language_keyboard())

@dp.message(F.text.regexp(r'^\d{6}$'))
async def tv_pair_code_handler(m: Message):
    await _track_incoming(m)
    if not m.from_user or not m.text:
        return
    code = m.text.strip()
    if len(code) != 6 or not code.isdigit():
        return
    lang = await get_user_language(m.from_user.id) or _telegram_lang(m.from_user)
    await _confirm_tv_pair_code(m, code, lang)

@dp.callback_query(F.data.startswith('lang:'))
async def language_handler(q: CallbackQuery):
    lang=q.data.split(':',1)[1]
    if lang not in {'hy','ru','en'}: lang='ru'
    await set_user_language(q.from_user.id, lang)
    await q.answer()
    title,body=TEXTS[lang]
    sent = await q.message.answer(f'{title}\n\n{body}')
    await _track_message(sent.chat.id, sent.message_id)
    if not ADMIN_ID or int(q.from_user.id) != int(ADMIN_ID):
        payment = await q.message.answer(
            {'hy':'💳 Ընտրեք վճարման եղանակը','ru':'💳 Выберите способ оплаты','en':'💳 Choose a payment method'}[lang],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text={'hy':'💵 Վճարել','ru':'💵 Оплатить','en':'💵 Pay'}[lang], callback_data='payment:choose')
            ]])
        )
        await _track_message(payment.chat.id, payment.message_id)
    menu = await q.message.answer(
        {'hy':'Ընտրեք գործողությունը ստորև։','ru':'Выберите действие внизу.','en':'Choose an action below.'}[lang],
        reply_markup=miniapp_keyboard(q.from_user.id, lang)
    )
    await _track_message(menu.chat.id, menu.message_id)

@dp.callback_query(F.data == 'payment:choose')
async def payment_choose_handler(q: CallbackQuery):
    uid = int(q.from_user.id)
    lang = await get_user_language(uid) or _telegram_lang(q.from_user)
    await q.answer()
    await q.message.answer(
        {'hy':'Ընտրեք վճարման եղանակը','ru':'Выберите способ оплаты','en':'Choose a payment method'}[lang],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💵 USDT TRC20', callback_data='payment:usdt')],
            [InlineKeyboardButton(text={'hy':'💳 Բանկային քարտ','ru':'💳 Банковская карта','en':'💳 Bank card'}[lang], callback_data='payment:card')],
        ])
    )

@dp.callback_query(F.data == 'payment:usdt')
async def payment_usdt_handler(q: CallbackQuery):
    uid = int(q.from_user.id)
    lang = await get_user_language(uid) or _telegram_lang(q.from_user)
    await q.answer()
    await set_setting(f'payment_method:{uid}', 'usdt')
    sent = await q.message.answer(
        PAYMENT_TEXT[lang],
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=PAY_BUTTON[lang], callback_data='payment:paid')
        ]])
    )
    await _track_message(sent.chat.id, sent.message_id)

@dp.callback_query(F.data == 'payment:card')
async def payment_card_handler(q: CallbackQuery):
    uid = int(q.from_user.id)
    lang = await get_user_language(uid) or _telegram_lang(q.from_user)
    await q.answer({'hy':'Հարցումն ուղարկված է','ru':'Запрос отправлен','en':'Request sent'}[lang], show_alert=True)
    await set_setting(f'payment_method:{uid}', 'card')
    try:
        if ADMIN_ID:
            name = str(q.from_user.full_name or uid)
            username = ('@' + q.from_user.username) if q.from_user.username else ''
            sent = await bot.send_message(
                ADMIN_ID,
                '💳 Abaj TV · оплата банковской картой\n'
                f'Пользователь: {name} {username}\n'
                f'Telegram ID: {uid}\n\n'
                'Пользователь хочет оплатить по карте.\n'
                '↩️ Ответьте на это сообщение номером карты — бот отправит ответ пользователю.'
            )
            await set_setting(f'card_payment_admin_msg:{int(sent.message_id)}', str(uid))
            await _track_message(sent.chat.id, sent.message_id)
    except Exception as exc:
        logging.warning('Card payment admin notify failed: %r', exc)
    sent = await q.message.answer(
        {'hy':'💳 Քարտով վճարման հարցումն ուղարկված է ադմինիստրատորին։ Նա կուղարկի քարտի համարը այստեղ։','ru':'💳 Запрос на оплату по карте отправлен администратору. Он пришлёт номер карты сюда.','en':'💳 Card payment request was sent to the administrator. The card number will be sent here.'}[lang]
    )
    await _track_message(sent.chat.id, sent.message_id)

@dp.callback_query(F.data == 'payment:paid')
async def payment_paid_handler(q: CallbackQuery):
    uid = int(q.from_user.id)
    lang = await get_user_language(uid) or _telegram_lang(q.from_user)
    if ADMIN_ID and uid == int(ADMIN_ID):
        await set_setting(f'edem_payment:{uid}', json.dumps({'status':'admin','last_paid_at':0,'plan_days':0,'last_amount':0}, separators=(',', ':')))
        await q.answer({'hy':'Ադմինին վճարում պետք չէ','ru':'Администратору оплата не требуется','en':'Admin does not need payment'}[lang], show_alert=True)
        return
    payment = {
        'status':'pending',
        'requested_at':int(time.time()),
        'last_paid_at':0,
        'plan_days':365,
        'last_amount':12,
    }
    await set_setting(f'edem_payment:{uid}', json.dumps(payment, ensure_ascii=False, separators=(',', ':')))
    await q.answer({'hy':'Ուղարկվել է ստուգման','ru':'Отправлено на проверку','en':'Sent for verification'}[lang], show_alert=True)
    try:
        if ADMIN_ID:
            name = str(q.from_user.full_name or uid)
            username = ('@' + q.from_user.username) if q.from_user.username else ''
            method = await get_setting(f'payment_method:{uid}', 'usdt')
            method_text = 'Банковская карта' if method == 'card' else 'USDT TRC20'
            sent = await bot.send_message(
                ADMIN_ID,
                '💳 Abaj TV: пользователь нажал «Оплатил»\n'
                f'Пользователь: {name} {username}\n'
                f'Telegram ID: {uid}\n'
                f'Способ: {method_text}\n'
                'Тариф: 12 месяцев · 12 USDT',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='✅ Получил', callback_data=f'payment:received:{uid}')
                ]])
            )
            await _track_message(sent.chat.id, sent.message_id)
    except Exception as exc:
        logging.warning('Payment admin notify failed: %r', exc)

@dp.callback_query(F.data.startswith('payment:received:'))
async def payment_received_handler(q: CallbackQuery):
    if not ADMIN_ID or int(q.from_user.id) != int(ADMIN_ID):
        await q.answer('Недоступно', show_alert=True)
        return
    try:
        uid = int(q.data.rsplit(':', 1)[1])
    except Exception:
        await q.answer('Ошибка ID', show_alert=True)
        return
    now = int(time.time())
    expires_at = now + 365 * 86400
    await set_setting(f'edem_expires_at:{uid}', str(expires_at))
    payment = {'status':'paid','last_paid_at':now,'plan_days':365,'last_amount':12}
    await set_setting(f'edem_payment:{uid}', json.dumps(payment, ensure_ascii=False, separators=(',', ':')))
    await q.answer('Доступ активирован на 12 месяцев', show_alert=True)
    try:
        lang = await get_user_language(uid) or 'ru'
        text = {
            'hy':'✅ Վճարումը հաստատված է։ Abaj TV ալիքները բացված են 12 ամսով։',
            'ru':'✅ Оплата подтверждена. Каналы Abaj TV открыты на 12 месяцев.',
            'en':'✅ Payment confirmed. Abaj TV channels are unlocked for 12 months.'
        }[lang]
        sent = await bot.send_message(uid, text, reply_markup=miniapp_keyboard(uid, lang))
        await _track_message(sent.chat.id, sent.message_id)
    except Exception as exc:
        logging.warning('Payment user notify failed: %r', exc)

@dp.message(F.reply_to_message & F.text)
async def support_reply_handler(m: Message):
    await _track_incoming(m)
    if not m.from_user or not m.reply_to_message or not m.text:
        return
    sender_id = int(m.from_user.id)
    replied_id = int(m.reply_to_message.message_id)

    # Admin replies with a bank card number for a card-payment request.
    if ADMIN_ID and sender_id == int(ADMIN_ID):
        raw_card_uid = await get_setting(f'card_payment_admin_msg:{replied_id}', '')
        try:
            card_uid = int(raw_card_uid or 0)
        except Exception:
            card_uid = 0
        if card_uid > 0:
            lang = await get_user_language(card_uid) or 'ru'
            sent = await bot.send_message(
                card_uid,
                ({'hy':'💳 Բանկային քարտի համարը՝\n\n','ru':'💳 Номер банковской карты для оплаты:\n\n','en':'💳 Bank card number for payment:\n\n'}[lang] + m.text),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=PAY_BUTTON[lang], callback_data='payment:paid')
                ]])
            )
            await _track_message(sent.chat.id, sent.message_id)
            await _answer(m, '✅ Номер карты отправлен пользователю.')
            return

    # Admin replies to a support message that came from the Mini App.
    if ADMIN_ID and sender_id == int(ADMIN_ID):
        raw_uid = await get_setting(f'support_admin_msg:{replied_id}', '')
        try:
            uid = int(raw_uid or 0)
        except Exception:
            uid = 0
        if uid > 0:
            try:
                sent = await bot.send_message(uid, '💬 Администратор Abaj TV:\n\n' + m.text)
                await set_setting(f'support_user_msg:{int(sent.message_id)}', str(uid))
                await _answer(m, '✅ Ответ отправлен пользователю.')
            except Exception as exc:
                logging.warning('Support reply to user failed: %r', exc)
                await _answer(m, '⚠️ Не удалось отправить ответ пользователю.')
            return

    # User replies in Telegram to the administrator's previous answer.
    raw_uid = await get_setting(f'support_user_msg:{replied_id}', '')
    try:
        mapped_uid = int(raw_uid or 0)
    except Exception:
        mapped_uid = 0
    if mapped_uid == sender_id and ADMIN_ID:
        try:
            name = str(m.from_user.full_name or sender_id)
            username = ('@' + m.from_user.username) if m.from_user.username else ''
            sent = await bot.send_message(
                ADMIN_ID,
                '💬 Abaj TV · ответ пользователя\n'
                f'Пользователь: {name} {username}\n'
                f'Telegram ID: {sender_id}\n\n'
                f'{m.text}\n\n'
                '↩️ Ответьте на это сообщение — ответ уйдёт пользователю.'
            )
            await set_setting(f'support_admin_msg:{int(sent.message_id)}', str(sender_id))
            await _answer(m, '✅ Сообщение отправлено администратору.')
        except Exception as exc:
            logging.warning('Support reply to admin failed: %r', exc)
            await _answer(m, '⚠️ Не удалось отправить сообщение администратору.')
        return


@dp.message(F.text == '🌐 Հայերեն / Русский / English')
async def change_language(m: Message):
    await _track_incoming(m)
    await send_language_picker(m)

@dp.message(F.text.in_({'⬇️ Ներբեռնել APK','⬇️ Скачать APK','⬇️ Download APK','📱 Ներբեռնել APK','📱 Скачать APK','📱 Download APK'}))
async def download_apk(m: Message):
    await _track_incoming(m)
    lang = await get_user_language(m.from_user.id if m.from_user else 0) or _telegram_lang(m.from_user)
    await _ensure_latest_menu(m, lang)
    apk_url = _apk_download_url()
    if not apk_url:
        return
    await _answer(
        m,
        {'hy':'📱 Ներբեռնեք Abaj TV APK-ը','ru':'📱 Скачайте APK Abaj TV','en':'📱 Download Abaj TV APK'}.get(lang, '📱 Скачайте APK Abaj TV'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text={'hy':'📱 Ներբեռնել APK','ru':'📱 Скачать APK','en':'📱 Download APK'}.get(lang, '📱 Скачать APK'),
                url=apk_url,
            )
        ]]),
    )

@dp.message(F.text.in_({'📺 Ներբեռնել APK TV-ի համար','📺 Скачать APK для TV','📺 Download APK for TV','🖥️ Ներբեռնել TV APK','🖥️ Скачать TV APK','🖥️ Download TV APK'}))
async def download_tv_apk(m: Message):
    await _track_incoming(m)
    lang = await get_user_language(m.from_user.id if m.from_user else 0) or _telegram_lang(m.from_user)
    await _ensure_latest_menu(m, lang)
    tv_apk_url = _tv_apk_download_url()
    qr_photo, start_link = await _tv_apk_qr_photo()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text={'hy':'⬇️ Ներբեռնել TV APK','ru':'⬇️ Скачать TV APK','en':'⬇️ Download TV APK'}.get(lang, '⬇️ Скачать TV APK'),
            url=tv_apk_url,
        )],
        *([[InlineKeyboardButton(
            text={'hy':'🤖 Բացել Abaj TV բոտը','ru':'🤖 Открыть бота Abaj TV','en':'🤖 Open Abaj TV bot'}.get(lang, '🤖 Открыть бота Abaj TV'),
            url=start_link,
        )]] if start_link else []),
    ])
    caption = {
        'hy':'📺 Android TV APK\n\n📷 Սկանավորեք QR կոդը՝ Abaj TV բոտը անմիջապես բացելու համար։',
        'ru':'📺 APK для Android TV\n\n📷 Сканируйте QR-код — сразу откроется бот Abaj TV.',
        'en':'📺 Android TV APK\n\n📷 Scan the QR code to open the Abaj TV bot directly.',
    }.get(lang, '📺 APK для Android TV\n\n📷 Сканируйте QR-код — сразу откроется бот Abaj TV.')
    if qr_photo:
        sent = await bot.send_photo(chat_id=m.chat.id, photo=qr_photo, caption=caption, reply_markup=keyboard)
        await _track_message(sent.chat.id, sent.message_id)
    else:
        await _answer(m, caption, reply_markup=keyboard)

@dp.message(F.text.in_({'📷 QR TV-ի համար','📷 QR для TV','📷 QR for TV'}))
async def show_tv_qr(m: Message):
    await _track_incoming(m)
    lang = await get_user_language(m.from_user.id if m.from_user else 0) or _telegram_lang(m.from_user)
    qr_photo, start_link = await _tv_apk_qr_photo()
    if not qr_photo:
        return await _answer(m, 'QR временно недоступен.')
    caption = {
        'hy':'📷 Սկանավորեք QR կոդը՝ Abaj TV բոտում TV APK-ը բացելու համար։',
        'ru':'📷 Сканируйте QR-код — откроется бот Abaj TV сразу на TV APK.',
        'en':'📷 Scan the QR code — Abaj TV bot opens directly on the TV APK.',
    }.get(lang, '📷 Сканируйте QR-код — откроется бот Abaj TV сразу на TV APK.')
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text={'hy':'🤖 Բացել բոտը','ru':'🤖 Открыть бота','en':'🤖 Open bot'}.get(lang, '🤖 Открыть бота'),
            url=start_link,
        )
    ]]) if start_link else None
    sent = await bot.send_photo(chat_id=m.chat.id, photo=qr_photo, caption=caption, reply_markup=markup)
    await _track_message(sent.chat.id, sent.message_id)

@dp.message(F.text.in_({'📤 Կիսվել','📤 Поделиться','📤 Share'}))
async def share_bot_qr(m: Message):
    await _track_incoming(m)
    lang = await get_user_language(m.from_user.id if m.from_user else 0) or _telegram_lang(m.from_user)
    start_link = await _bot_start_link('share')
    if not start_link:
        return await _answer(m, 'QR временно недоступен.')
    image = qrcode.make(start_link)
    buf = BytesIO()
    image.save(buf, format='PNG')
    qr_photo = BufferedInputFile(buf.getvalue(), filename='AbajTV-share-QR.png')
    caption = {
        'hy':'📤 Կիսվել Abaj TV-ով\n\n📷 Թող մարդը սկանավորի QR կոդը — բոտը անմիջապես կբացվի։',
        'ru':'📤 Поделиться Abaj TV\n\n📷 Пусть человек сканирует QR-код — сразу откроется бот Abaj TV.',
        'en':'📤 Share Abaj TV\n\n📷 Let the person scan the QR code — the Abaj TV bot opens directly.',
    }.get(lang, '📤 Поделиться Abaj TV\n\n📷 Пусть человек сканирует QR-код — сразу откроется бот Abaj TV.')
    sent = await bot.send_photo(chat_id=m.chat.id, photo=qr_photo, caption=caption)
    await _track_message(sent.chat.id, sent.message_id)

@dp.message(F.text)
async def text_handler(m: Message):
    await _track_incoming(m)
    lang=await get_user_language(m.from_user.id if m.from_user else 0) or 'ru'
    msg={'hy':'Բացեք Abaj TV Mini App-ը 👇','ru':'Откройте Abaj TV Mini App 👇','en':'Open Abaj TV Mini App 👇'}[lang]
    await _answer(m, msg, reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None,lang))

@dp.message()
async def other_handler(m: Message):
    await _track_incoming(m)
    lang=await get_user_language(m.from_user.id if m.from_user else 0) or 'ru'
    msg={'hy':'Abaj TV ալիքները բացվում են Mini App-ում 👇','ru':'Каналы Abaj TV открываются внутри Mini App 👇','en':'Abaj TV channels open inside the Mini App 👇'}[lang]
    await _answer(m, msg, reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None,lang))

async def main():
    global bot
    logging.info('Abaj TV build: %s', BUILD_VERSION)
    logging.info('Abaj TV persistent data: %s', DATA_DIR)
    logging.info('Abaj TV SQLite DB: %s', DB_PATH)

    if not TELEGRAM_BOT_TOKEN:
        raw = {
            'FACETALK_BOT_TOKEN': os.getenv('FACETALK_BOT_TOKEN', ''),
            'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN', ''),
            'BOT_TOKEN': os.getenv('BOT_TOKEN', ''),
        }
        diag = ', '.join(
            f"{k}:present={bool(v)},len={len(v.strip())},colon={':' in v}" for k,v in raw.items()
        )
        raise RuntimeError(
            'NO VALID TELEGRAM BOT TOKEN. Railway variables were read but none has the Telegram format '
            'digits:secret. Safe diagnostics: ' + diag + '. In Railway paste ONLY the BotFather token value, '
            'not the variable name, @username, URL, or quotes.'
        )

    logging.info('Using Telegram token from Railway variable %s', TELEGRAM_BOT_TOKEN_SOURCE)
    try:
        bot = Bot(TELEGRAM_BOT_TOKEN)
    except Exception as exc:
        raise RuntimeError(
            f'Telegram token from {TELEGRAM_BOT_TOKEN_SOURCE or "unknown variable"} is malformed. '
            'Paste only the BotFather token in digits:secret format.'
        ) from exc

    try:
        await bot.set_my_name(name="Abaj TV")
        await bot.set_my_short_description(short_description="Армянские и российские IPTV каналы")
        await bot.set_my_description(description="Abaj TV — армянские и российские телеканалы, поиск, избранное и TV режим.")
    except Exception as exc:
        logging.warning("Telegram bot profile rename skipped: %r", exc)

    me = await bot.get_me()
    actual_username = (me.username or '').lstrip('@')
    logging.info('Abaj TV Telegram bot authenticated as @%s (id=%s)', actual_username, me.id)
    if EXPECTED_BOT_USERNAME and actual_username.lower() != EXPECTED_BOT_USERNAME.lower():
        raise RuntimeError(
            f'WRONG TELEGRAM BOT TOKEN: expected @{EXPECTED_BOT_USERNAME}, '
            f'but Railway token belongs to @{actual_username}. '
            'Set FACETALK_BOT_TOKEN to the BotFather token for the FaceTalk bot.'
        )

    migrated = migrate_legacy_db()
    if migrated:
        logging.info('Legacy FaceTalk DB migrated into persistent Volume')
    await init_db()
    await start_webapp(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
