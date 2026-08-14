import asyncio
import logging
import hashlib
import hmac
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from .config import TELEGRAM_BOT_TOKEN, MINIAPP_URL, DATA_DIR, DB_PATH
from .db import init_db
from .webapp import start_webapp
from .storage import migrate_legacy_db

logging.basicConfig(level=logging.INFO)

bot = Bot(TELEGRAM_BOT_TOKEN)
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

def miniapp_keyboard(user_id: int | None = None):
    if not MINIAPP_URL:
        return None
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="✨ Открыть FaceTalk",
                web_app=WebAppInfo(url=_miniapp_url_for_user(user_id))
            )
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )

@dp.message(CommandStart())
async def start_handler(m: Message):
    if not MINIAPP_URL:
        await m.answer(
            "FaceTalk Mini App ещё не настроен. Добавь MINIAPP_URL в Railway."
        )
        return
    await m.answer(
        "✨ FaceTalk AI\n\nОткрой Mini App — всё общение, фото, голос, видео и админка находятся внутри.",
        reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None)
    )

@dp.message(F.text)
async def text_handler(m: Message):
    # Telegram-чат намеренно отключён: вся логика только в Mini App.
    await m.answer(
        "Открой FaceTalk Mini App 👇",
        reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None)
    )

@dp.message()
async def other_handler(m: Message):
    await m.answer(
        "Фото, голос и видео работают только внутри Mini App 👇",
        reply_markup=miniapp_keyboard(m.from_user.id if m.from_user else None)
    )

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
