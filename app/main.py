import asyncio
import os
import logging
import hashlib
import hmac
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_TOKEN_SOURCE, MINIAPP_URL, DATA_DIR, DB_PATH, EXPECTED_BOT_USERNAME
from .db import init_db, set_user_language, get_user_language
from .webapp import start_webapp
from .storage import migrate_legacy_db

logging.basicConfig(level=logging.INFO)
BUILD_VERSION = 'v3.5.0-logo-lang-splash'

bot = None
dp = Dispatcher()

def _miniapp_url_for_user(user_id: int | None):
    """Add a short-lived signed fallback login for Telegram clients that sometimes omit initData."""
    if not MINIAPP_URL or not user_id:
        return MINIAPP_URL
    ts = int(time.time())
    payload = f"{int(user_id)}:{ts}"
    sig = hmac.new(TELEGRAM_BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    parts = urlsplit(MINIAPP_URL)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update({'ft_uid': str(int(user_id)), 'ft_ts': str(ts), 'ft_sig': sig})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

def miniapp_keyboard(user_id: int | None = None, lang: str = 'ru'):
    if not MINIAPP_URL:
        return None
    labels={'hy':'✨ Բացել FaceTalk','ru':'✨ Открыть FaceTalk','en':'✨ Open FaceTalk'}
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=labels.get(lang, labels['ru']), web_app=WebAppInfo(url=_miniapp_url_for_user(user_id)))],
                  [KeyboardButton(text='🌐 Հայերեն / Русский / English')]],
        resize_keyboard=True,
        is_persistent=True,
    )

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🇦🇲 Հայերեն', callback_data='lang:hy')],
        [InlineKeyboardButton(text='🇷🇺 Русский', callback_data='lang:ru')],
        [InlineKeyboardButton(text='🇬🇧 English', callback_data='lang:en')],
    ])

TEXTS={
 'hy':('✨ FaceTalk AI','Բացեք Mini App-ը և սկսեք զրույցը լուսանկարով, ձայնով և տեսապատասխաններով։'),
 'ru':('✨ FaceTalk AI','Откройте Mini App и начните общение с фото, голосом и видеоответами.'),
 'en':('✨ FaceTalk AI','Open the Mini App and start chatting with photo, voice and video replies.'),
}

async def send_language_picker(m: Message):
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media', 'facetalk_logo.png')
    caption='✨ FaceTalk AI\n\n🇦🇲 Ընտրեք լեզուն\n🇷🇺 Выберите язык\n🇬🇧 Choose language'
    if os.path.exists(logo_path):
        await m.answer_photo(FSInputFile(logo_path), caption=caption, reply_markup=language_keyboard())
    else:
        await m.answer(caption, reply_markup=language_keyboard())

@dp.message(CommandStart())
async def start_handler(m: Message):
    if not MINIAPP_URL:
        await m.answer('FaceTalk Mini App ещё не настроен. Добавь MINIAPP_URL в Railway.')
        return
    await send_language_picker(m)

@dp.callback_query(F.data.startswith('lang:'))
async def language_handler(q: CallbackQuery):
    lang=q.data.split(':',1)[1]
    if lang not in {'hy','ru','en'}: lang='ru'
    await set_user_language(q.from_user.id, lang)
    await q.answer()
    title,body=TEXTS[lang]
    await q.message.answer(f'{title}\n\n{body}', reply_markup=miniapp_keyboard(q.from_user.id, lang))

@dp.message(F.text == '🌐 Հայերեն / Русский / English')
async def change_language(m: Message):
    await send_language_picker(m)

@dp.message(F.text)
async def text_handler(m: Message):
    lang=await get_user_language(m.from_user.id if m.from_user else 0) or 'ru'
    msg={'hy':'Բացեք FaceTalk Mini App-ը 👇','ru':'Откройте FaceTalk Mini App 👇','en':'Open FaceTalk Mini App 👇'}[lang]
    await m.answer(msg, reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None,lang))

@dp.message()
async def other_handler(m: Message):
    lang=await get_user_language(m.from_user.id if m.from_user else 0) or 'ru'
    msg={'hy':'Լուսանկարը, ձայնը և տեսանյութը աշխատում են Mini App-ի ներսում 👇','ru':'Фото, голос и видео работают внутри Mini App 👇','en':'Photo, voice and video work inside the Mini App 👇'}[lang]
    await m.answer(msg, reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None,lang))

async def main():
    global bot
    logging.info('FaceTalk build: %s', BUILD_VERSION)
    logging.info('FaceTalk persistent data: %s', DATA_DIR)
    logging.info('FaceTalk SQLite DB: %s', DB_PATH)

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

    # Fail fast if Railway still contains a token from another project.
    # This prevents FaceTalk code from silently polling @PokerArmenia_bot or any other bot.
    me = await bot.get_me()
    actual_username = (me.username or '').lstrip('@')
    logging.info('FaceTalk Telegram bot authenticated as @%s (id=%s)', actual_username, me.id)
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
