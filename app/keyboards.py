from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from .roles import ROLES
from .config import MINIAPP_URL

def main_menu():
    rows = []
    if MINIAPP_URL:
        rows.append([InlineKeyboardButton(text='✨ Открыть FaceTalk Mini App', web_app=WebAppInfo(url=MINIAPP_URL))])
    rows += [
        [InlineKeyboardButton(text='📸 Загрузить фото', callback_data='upload_photo')],
        [InlineKeyboardButton(text='🎭 Выбрать тему', callback_data='choose_role')],
        [InlineKeyboardButton(text='🎥 Видео / 🔊 Голос', callback_data='reply_mode')],
        [InlineKeyboardButton(text='🎬 Начать общение', callback_data='start_chat')],
        [InlineKeyboardButton(text='🧹 Новый разговор', callback_data='reset_chat')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def roles_menu():
    rows = [[InlineKeyboardButton(text=title, callback_data=f'role:{key}')] for key, (title, _) in ROLES.items()]
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def mode_menu(current='video'):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=('✅ ' if current=='video' else '')+'🎥 Видеоответ', callback_data='mode:video')],
        [InlineKeyboardButton(text=('✅ ' if current=='voice' else '')+'🔊 Только голос', callback_data='mode:voice')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='back')],
    ])
