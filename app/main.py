import asyncio
import logging
import hashlib
import hmac
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
)

from .config import TELEGRAM_BOT_TOKEN, MINIAPP_URL, DATA_DIR, DB_PATH
from .db import init_db, get_setting, set_setting
from .webapp import start_webapp
from .storage import migrate_legacy_db

BASE_DIR = __import__("os").path.dirname(__import__("os").path.dirname(__file__))
START_LOGO = __import__("os").path.join(BASE_DIR, "media", "facetalk_logo.png")

logging.basicConfig(level=logging.INFO)

bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

LANGS = {
    "hy": {
        "button": "🇦🇲 Հայերեն",
        "open": "✨ Բացել FaceTalk",
        "welcome": "✨ FaceTalk AI\n\nԲացիր Mini App-ը․ լուսանկարը, ձայնը, տեսազանգը և բոլոր կարգավորումները ներսում են։",
        "hint": "Ընտրիր լեզուն 👇",
        "text_fallback": "Բացիր FaceTalk Mini App-ը 👇",
        "media_fallback": "Լուսանկարը, ձայնը և տեսանյութը աշխատում են Mini App-ի ներսում 👇",
    },
    "ru": {
        "button": "🇷🇺 Русский",
        "open": "✨ Открыть FaceTalk",
        "welcome": "✨ FaceTalk AI\n\nОткрой Mini App — фото, голос, видео и все настройки находятся внутри.",
        "hint": "Выбери язык 👇",
        "text_fallback": "Открой FaceTalk Mini App 👇",
        "media_fallback": "Фото, голос и видео работают только внутри Mini App 👇",
    },
    "en": {
        "button": "🇬🇧 English",
        "open": "✨ Open FaceTalk",
        "welcome": "✨ FaceTalk AI\n\nOpen the Mini App — photo, voice, video and all settings are inside.",
        "hint": "Choose a language 👇",
        "text_fallback": "Open the FaceTalk Mini App 👇",
        "media_fallback": "Photo, voice and video work inside the Mini App 👇",
    },
}


def _lang_key(user_id: int) -> str:
    return f"bot_lang:{int(user_id)}"


async def _get_lang(user_id: int | None) -> str:
    if not user_id:
        return "ru"
    value = (await get_setting(_lang_key(user_id), "")).strip().lower()
    return value if value in LANGS else "ru"


def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANGS["hy"]["button"], callback_data="lang:hy")],
            [InlineKeyboardButton(text=LANGS["ru"]["button"], callback_data="lang:ru")],
            [InlineKeyboardButton(text=LANGS["en"]["button"], callback_data="lang:en")],
        ]
    )


def _miniapp_url_for_user(user_id: int | None, lang: str = "ru"):
    """Add signed fallback login + selected language for Telegram clients."""
    if not MINIAPP_URL or not user_id:
        return MINIAPP_URL
    ts = int(time.time())
    payload = f"{int(user_id)}:{ts}"
    sig = hmac.new(TELEGRAM_BOT_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    parts = urlsplit(MINIAPP_URL)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update({
        "ft_uid": str(int(user_id)),
        "ft_ts": str(ts),
        "ft_sig": sig,
        "ft_lang": lang if lang in LANGS else "ru",
        # cache buster so Telegram does not keep an old Mini App shell
        "ft_v": "346",
    })
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


def miniapp_keyboard(user_id: int | None = None, lang: str = "ru"):
    if not MINIAPP_URL:
        return None
    strings = LANGS.get(lang, LANGS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(
            text=strings["open"],
            web_app=WebAppInfo(url=_miniapp_url_for_user(user_id, lang))
        )]],
        resize_keyboard=True,
        is_persistent=True,
    )


@dp.message(CommandStart())
async def start_handler(m: Message):
    if not MINIAPP_URL:
        await m.answer("FaceTalk Mini App ещё не настроен. Добавь MINIAPP_URL в Railway.")
        return
    # Always show the FaceTalk logo + all three languages at /start.
    caption = "FaceTalk AI\n\n🌐 Ընտրեք լեզուն / Выберите язык / Choose language"
    try:
        await m.answer_photo(
            FSInputFile(START_LOGO),
            caption=caption,
            reply_markup=_language_keyboard(),
        )
    except Exception:
        logging.exception("Could not send FaceTalk start logo")
        await m.answer(caption, reply_markup=_language_keyboard())


@dp.callback_query(F.data.startswith("lang:"))
async def language_handler(q: CallbackQuery):
    code = (q.data or "").split(":", 1)[-1].lower()
    if code not in LANGS:
        await q.answer("Language error", show_alert=True)
        return
    uid = q.from_user.id
    await set_setting(_lang_key(uid), code)
    strings = LANGS[code]
    try:
        await q.message.edit_text(f"✅ {strings['button']}\n\n{strings['hint']}")
    except Exception:
        pass
    await q.message.answer(
        strings["welcome"],
        reply_markup=miniapp_keyboard(uid, code),
    )
    await q.answer()


@dp.message(F.text)
async def text_handler(m: Message):
    uid = m.from_user.id if m.from_user else None
    lang = await _get_lang(uid)
    strings = LANGS[lang]
    await m.answer(strings["text_fallback"], reply_markup=miniapp_keyboard(uid, lang))


@dp.message()
async def other_handler(m: Message):
    uid = m.from_user.id if m.from_user else None
    lang = await _get_lang(uid)
    strings = LANGS[lang]
    await m.answer(strings["media_fallback"], reply_markup=miniapp_keyboard(uid, lang))


async def main():
    logging.info('FaceTalk persistent data: %s', DATA_DIR)
    logging.info('FaceTalk SQLite DB: %s', DB_PATH)
    migrated = migrate_legacy_db()
    if migrated:
        logging.info('Legacy FaceTalk DB migrated into persistent Volume')
    await init_db()
    await start_webapp(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
