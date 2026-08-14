import asyncio
import os
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile

from .config import BOT_TOKEN, DID_API_KEY, MINIAPP_URL
from .db import init_db, get_user, set_photo, set_role, set_reply_mode, reset_history, append_history
from .roles import ROLES
from .keyboards import main_menu, roles_menu, mode_menu
from .ai import chat, transcribe, synthesize
from .avatar import create_video
from .webapp import start_webapp

if not BOT_TOKEN:
    raise RuntimeError('Set TELEGRAM_BOT_TOKEN')

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
waiting_photo = set()

WELCOME = (
    '✨ <b>FaceTalk AI</b>\n\n'
    'Загрузи фото, выбери тему и общайся с AI-собеседником текстом или голосом.\n\n'
    '🎥 В режиме Видео лицо на фото оживает и говорит ответ.\n'
    '🔊 Если видео-сервис недоступен, бот автоматически пришлёт голос — разговор не прервётся.'
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
    if key in ROLES:
        await set_role(c.from_user.id, key)
        await c.message.edit_text(f'✅ Выбрано: {ROLES[key][0]}\n\nТеперь можешь писать или отправить голосовое.', reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == 'reply_mode')
async def reply_mode(c: CallbackQuery):
    u=await get_user(c.from_user.id)
    await c.message.edit_text('Выбери формат ответа:', reply_markup=mode_menu(u['reply_mode']))
    await c.answer()

@dp.callback_query(F.data.startswith('mode:'))
async def mode_selected(c: CallbackQuery):
    mode=c.data.split(':',1)[1]
    await set_reply_mode(c.from_user.id,mode)
    await c.message.edit_text(('🎥 Видеоответ включён.' if mode=='video' else '🔊 Голосовой ответ включён.'), reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == 'start_chat')
async def start_chat(c: CallbackQuery):
    u = await get_user(c.from_user.id)
    photo = '✅ фото загружено' if u['photo_file_id'] else '⚠️ сначала загрузи фото для видео'
    mode='🎥 Видео' if u['reply_mode']=='video' else '🔊 Голос'
    await c.message.answer(f'🎬 Общение запущено. {photo}.\nРоль: {ROLES[u["role"]][0]}\nРежим: {mode}\n\nНапиши сообщение или отправь голосовое.')
    await c.answer()

@dp.callback_query(F.data == 'reset_chat')
async def reset(c: CallbackQuery):
    await reset_history(c.from_user.id)
    await c.message.answer('🧹 История разговора очищена. Фото и роль сохранены.', reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == 'back')
async def back(c: CallbackQuery):
    await c.message.edit_text('FaceTalk AI', reply_markup=main_menu())
    await c.answer()

async def _photo_bytes(file_id: str):
    f=await bot.get_file(file_id)
    fd,p=tempfile.mkstemp(suffix='.jpg'); os.close(fd)
    try:
        await bot.download_file(f.file_path,destination=p)
        with open(p,'rb') as x: return x.read()
    finally:
        try: os.remove(p)
        except OSError: pass

async def answer_user(m: Message, text: str):
    u = await get_user(m.from_user.id)
    thinking = await m.answer('✨ Думаю…')
    try:
        reply = await chat(u['role'], u['history'], text)
    except Exception as e:
        try: await thinking.delete()
        except Exception: pass
        await m.answer('⚠️ AI сейчас не смог ответить. Проверь OPENAI_API_KEY / OPENAI_TEXT_MODEL в Railway.\n\nОшибка: ' + str(e)[:250])
        return
    try: await thinking.delete()
    except Exception: pass
    await append_history(m.from_user.id, 'user', text)
    await append_history(m.from_user.id, 'assistant', reply)
    await m.answer(reply)
    audio_path = await synthesize(reply)
    if not audio_path: return
    try:
        if u['reply_mode']=='video' and u['photo_file_id']:
            wait=await m.answer('🎥 Создаю видеоответ…')
            video_path=await create_video(await _photo_bytes(u['photo_file_id']), audio_path)
            try: await wait.delete()
            except Exception: pass
            if video_path:
                try: await m.answer_video(FSInputFile(video_path), caption='✨ FaceTalk AI')
                finally:
                    try: os.remove(video_path)
                    except OSError: pass
                return
            await m.answer('⚡ Видео сейчас недоступно — отправляю голосовой ответ.')
        await m.answer_voice(FSInputFile(audio_path))
    finally:
        try: os.remove(audio_path)
        except OSError: pass

@dp.message(F.voice)
async def voice(m: Message):
    file = await bot.get_file(m.voice.file_id)
    fd, path = tempfile.mkstemp(suffix='.ogg'); os.close(fd)
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
    if m.text.startswith('/'): return
    await answer_user(m, m.text)

async def main():
    os.makedirs('data', exist_ok=True)
    await init_db()
    runner = await start_webapp(bot)
    print('FaceTalk web server started. MiniApp URL:', MINIAPP_URL or '(set MINIAPP_URL after Railway domain is created)')
    print('D-ID video:', 'configured' if DID_API_KEY else 'not configured, voice fallback active')
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()

if __name__ == '__main__': asyncio.run(main())
