import asyncio
import os
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile

from .config import BOT_TOKEN, DID_API_KEY, MINIAPP_URL, ADMIN_ID, OPENAI_INPUT_USD_PER_1M, OPENAI_OUTPUT_USD_PER_1M, OPENAI_TTS_USD_PER_1M_CHARS, DID_USD_PER_VIDEO
from .db import init_db, get_user, set_photo, set_role, set_reply_mode, reset_history, append_history, add_usage, video_remaining, admin_stats, set_global_video_limit, set_provider_state, get_provider_state
from .roles import ROLES
from .keyboards import main_menu, roles_menu, mode_menu, admin_menu
from .ai import chat, transcribe, synthesize
from .avatar import create_video
from .webapp import start_webapp
from .billing import real_openai_costs

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
    await m.answer(WELCOME, reply_markup=main_menu(m.from_user.id), parse_mode='HTML')

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
        await c.message.edit_text(f'✅ Выбрано: {ROLES[key][0]}\n\nТеперь можешь писать или отправить голосовое.', reply_markup=main_menu(c.from_user.id))
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
    await c.message.edit_text(('🎥 Видеоответ включён.' if mode=='video' else '🔊 Голосовой ответ включён.'), reply_markup=main_menu(c.from_user.id))
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
    await c.message.answer('🧹 История разговора очищена. Фото и роль сохранены.', reply_markup=main_menu(c.from_user.id))
    await c.answer()

@dp.callback_query(F.data == 'back')
async def back(c: CallbackQuery):
    await c.message.edit_text('FaceTalk AI', reply_markup=main_menu(c.from_user.id))
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
        reply, usage = await chat(u['role'], u['history'], text)
        provider = usage.get('provider','unknown')
        await set_provider_state(provider,'ok',f'Последний AI-запрос успешен через {provider}')
        await add_usage(m.from_user.id, text_requests=1, input_tokens=usage.get('input_tokens',0), output_tokens=usage.get('output_tokens',0))
    except Exception as e:
        try: await thinking.delete()
        except Exception: pass
        err = str(e)
        low = err.lower()
        if 'groq' in low:
            provider_name = 'groq'
            key_name = 'GROQ_API_KEY'
        else:
            provider_name = 'openai'
            key_name = 'OPENAI_API_KEY'
        if '401' in err or 'incorrect api key' in low or 'invalid_api_key' in low:
            hint = f'{key_name} неверный.'
            await set_provider_state(provider_name,'bad_key',err)
        elif '429' in err or 'quota' in low or 'billing' in low or 'no credits remaining' in low or 'rate limit' in low:
            hint = 'Основной AI временно упёрся в лимит. Если настроен второй провайдер, он используется автоматически.'
            await set_provider_state(provider_name,'limit',err)
        else:
            hint = 'Проверь GROQ_API_KEY. OpenAI теперь только резерв.'
            await set_provider_state(provider_name,'error',err)
        await m.answer('⚠️ FaceTalk не получил ответ от AI.\n' + hint + '\n\nОшибка: ' + err[:300])
        return
    try: await thinking.delete()
    except Exception: pass
    await append_history(m.from_user.id, 'user', text)
    await append_history(m.from_user.id, 'assistant', reply)
    await m.answer(reply)
    audio_path, tts_provider = await synthesize(reply)
    if not audio_path: return
    if tts_provider == 'openai':
        await add_usage(m.from_user.id, tts_chars=len(reply))
    try:
        if u['reply_mode']=='video' and u['photo_file_id']:
            quota=await video_remaining(m.from_user.id)
            if quota['remaining'] <= 0:
                await m.answer(f'⚠️ Дневной лимит видео исчерпан: {quota["used"]}/{quota["limit"]}. Отправляю голос.')
                await m.answer_voice(FSInputFile(audio_path)); return
            await add_usage(m.from_user.id, video_attempts=1)
            wait=await m.answer(f'🎥 Создаю видеоответ… Осталось сегодня: {quota["remaining"]}')
            video_path=await create_video(await _photo_bytes(u['photo_file_id']), audio_path)
            try: await wait.delete()
            except Exception: pass
            if video_path:
                await add_usage(m.from_user.id, video_success=1)
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
        text, stt_provider = await transcribe(path)
        await set_provider_state(stt_provider,'ok',f'Распознавание голоса работает через {stt_provider}')
        if not text:
            await m.answer('Не удалось распознать голос. Проверь GROQ_API_KEY.')
            return
        await m.answer(f'🎙️ <i>{text}</i>', parse_mode='HTML')
        await answer_user(m, text)
    finally:
        try: os.remove(path)
        except OSError: pass

@dp.callback_query(F.data == 'admin_stats')
async def admin_stats_cb(c: CallbackQuery):
    if not ADMIN_ID or c.from_user.id != ADMIN_ID:
        await c.answer('Нет доступа', show_alert=True)
        return

    st = await admin_stats()
    t = st['today']
    a = st['all']
    state = await get_provider_state('openai')
    real = await real_openai_costs()

    def estimate(row):
        return (
            row[1] * OPENAI_INPUT_USD_PER_1M / 1_000_000
            + row[2] * OPENAI_OUTPUT_USD_PER_1M / 1_000_000
            + row[3] * OPENAI_TTS_USD_PER_1M_CHARS / 1_000_000
            + row[5] * DID_USD_PER_VIDEO
        )

    labels = {
        'ok': '✅ Работает',
        'no_credits': '❌ Нет кредитов',
        'bad_key': '🔑 Неверный ключ',
        'error': '⚠️ Ошибка',
        'unknown': '❔ Ещё не проверен',
    }
    state_label = labels.get(state.get('state', 'unknown'), '❔ Неизвестно')

    real_today = f"${real['today']['usd']:.4f}" if real['today']['ok'] else "н/д"
    real_month = f"${real['month']['usd']:.4f}" if real['month']['ok'] else "н/д"

    cost_note = ""
    if not real['today']['ok']:
        cost_note = "\n⚠️ Costs API: " + str(real['today']['error'])[:160]

    txt = (
        "⚙️ <b>FaceTalk — расходы</b>\n\n"
        "🤖 <b>OpenAI</b>\n"
        f"Статус: <b>{state_label}</b>\n"
        f"💵 Реально сегодня: <b>{real_today}</b>\n"
        f"📆 Реально с начала месяца: <b>{real_month}</b>\n"
        f"🔎 Scope: <code>{real['scope']}</code>{cost_note}\n\n"
        f"👥 Пользователей: <b>{st['users']}</b>\n"
        f"📅 Локальная статистика сегодня ({st['day']})\n"
        f"💬 AI запросов: {t[0]}\n"
        f"🔤 Токены: {t[1]} вход / {t[2]} выход\n"
        f"🔊 TTS символов: {t[3]}\n"
        f"🎥 D-ID видео: {t[5]} готово / {t[4]} попыток\n"
        f"🧮 Локальная оценка сегодня: <b>${estimate(t):.4f}</b>\n\n"
        f"📊 За всё время: AI {a[0]}, видео {a[5]}\n"
        f"🧮 Локальная оценка всего: <b>${estimate(a):.4f}</b>\n\n"
        f"🎛 Лимит видео: <b>{st['video_limit']}/день на пользователя</b>\n\n"
        "ℹ️ Реальные суммы OpenAI берутся из Organization Costs API. "
        "Точный остаток prepaid-кредитов этот API не возвращает."
    )
    await c.message.edit_text(txt, parse_mode='HTML', reply_markup=admin_menu(st['video_limit']))
    await c.answer()

@dp.callback_query(F.data.startswith('admin_limit:'))
async def admin_limit_cb(c: CallbackQuery):
    if not ADMIN_ID or c.from_user.id != ADMIN_ID:
        await c.answer('Нет доступа',show_alert=True); return
    st=await admin_stats(); delta=int(c.data.split(':',1)[1]); await set_global_video_limit(st['video_limit']+delta)
    await admin_stats_cb(c)

@dp.callback_query(F.data == 'admin_noop')
async def admin_noop(c: CallbackQuery): await c.answer()

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
