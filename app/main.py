import asyncio
import os
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile

from .config import BOT_TOKEN
from .db import init_db, get_user, set_photo, set_role, append_history
from .roles import ROLES
from .keyboards import main_menu, roles_menu
from .ai import chat, transcribe, synthesize

if not BOT_TOKEN:
    raise RuntimeError('Set TELEGRAM_BOT_TOKEN in .env')

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
waiting_photo = set()

WELCOME = (
    '✨ <b>FaceTalk AI</b>\n\n'
    'Загрузи фото, выбери тему и общайся с AI-собеседником текстом или голосом. '
    'Бот помнит текущий разговор и отвечает голосом.\n\n'
    '🎥 Модуль реалистичного talking-avatar видео подготовлен для подключения отдельного видео API.'
)

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(WELCOME, reply_markup=main_menu(), parse_mode='HTML')

@dp.callback_query(F.data == 'upload_photo')
async def ask_photo(c: CallbackQuery):
    waiting_photo.add(c.from_user.id)
    await c.message.answer('📸 Отправь фотографию лица. Лучше анфас, хорошее освещение, без сильных фильтров.')
    await c.answer()

@dp.message(F.photo)
async def photo(m: Message):
    await set_photo(m.from_user.id, m.photo[-1].file_id)
    waiting_photo.discard(m.from_user.id)
    await m.answer('✅ Фото сохранено. Теперь выбери тему.', reply_markup=roles_menu())

@dp.callback_query(F.data == 'choose_role')
async def choose_role(c: CallbackQuery):
    await c.message.edit_text('🎭 Кем должен быть твой AI-собеседник?', reply_markup=roles_menu())
    await c.answer()

@dp.callback_query(F.data.startswith('role:'))
async def role_selected(c: CallbackQuery):
    key = c.data.split(':', 1)[1]
    await set_role(c.from_user.id, key)
    await c.message.edit_text(f'✅ Выбрано: {ROLES[key][0]}\n\nТеперь можешь писать или отправить голосовое.', reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == 'start_chat')
async def start_chat(c: CallbackQuery):
    u = await get_user(c.from_user.id)
    photo = '✅ фото загружено' if u['photo_file_id'] else '⚠️ фото ещё не загружено'
    await c.message.answer(f'🎥 Режим общения запущен. {photo}.\nРоль: {ROLES[u["role"]][0]}\n\nНапиши сообщение или отправь голосовое.')
    await c.answer()

@dp.callback_query(F.data == 'reset_chat')
async def reset(c: CallbackQuery):
    u = await get_user(c.from_user.id)
    await set_role(c.from_user.id, u['role'])
    await c.message.answer('🧹 История разговора очищена. Фото и выбранная роль сохранены.', reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == 'back')
async def back(c: CallbackQuery):
    await c.message.edit_text('FaceTalk AI', reply_markup=main_menu())
    await c.answer()

async def answer_user(m: Message, text: str):
    u = await get_user(m.from_user.id)
    reply = await chat(u['role'], u['history'], text)
    await append_history(m.from_user.id, 'user', text)
    await append_history(m.from_user.id, 'assistant', reply)
    await m.answer(reply)
    audio_path = await synthesize(reply)
    if audio_path:
        try:
            await m.answer_voice(FSInputFile(audio_path))
        finally:
            try: os.remove(audio_path)
            except OSError: pass

@dp.message(F.voice)
async def voice(m: Message):
    file = await bot.get_file(m.voice.file_id)
    fd, path = tempfile.mkstemp(suffix='.ogg')
    os.close(fd)
    try:
        await bot.download_file(file.file_path, destination=path)
        text = await transcribe(path)
        if not text:
            await m.answer('Не удалось распознать голос. Проверь OPENAI_API_KEY.')
            return
        await m.answer(f'🎙️ <i>{text}</i>', parse_mode='HTML')
        await answer_user(m, text)
    finally:
        try: os.remove(path)
        except OSError: pass

@dp.message(F.text)
async def text(m: Message):
    if m.text.startswith('/'):
        return
    await answer_user(m, m.text)

async def main():
    os.makedirs('data', exist_ok=True)
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
