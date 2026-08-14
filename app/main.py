import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from .config import TELEGRAM_BOT_TOKEN, MINIAPP_URL
from .db import init_db
from .webapp import start_webapp

logging.basicConfig(level=logging.INFO)

bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

def miniapp_keyboard():
    if not MINIAPP_URL:
        return None
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="✨ Открыть FaceTalk",
                web_app=WebAppInfo(url=MINIAPP_URL)
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
        reply_markup=miniapp_keyboard()
    )

@dp.message(F.text)
async def text_handler(m: Message):
    # Telegram-чат намеренно отключён: вся логика только в Mini App.
    await m.answer(
        "Открой FaceTalk Mini App 👇",
        reply_markup=miniapp_keyboard()
    )

@dp.message()
async def other_handler(m: Message):
    await m.answer(
        "Фото, голос и видео работают только внутри Mini App 👇",
        reply_markup=miniapp_keyboard()
    )

async def main():
    await init_db()
    await start_webapp(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
