from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .roles import ROLES

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📸 Загрузить фото', callback_data='upload_photo')],
        [InlineKeyboardButton(text='🎭 Выбрать тему', callback_data='choose_role')],
        [InlineKeyboardButton(text='🎥 Начать общение', callback_data='start_chat')],
        [InlineKeyboardButton(text='🧹 Новый разговор', callback_data='reset_chat')],
    ])

def roles_menu():
    rows = [[InlineKeyboardButton(text=title, callback_data=f'role:{key}')] for key, (title, _) in ROLES.items()]
    rows.append([InlineKeyboardButton(text='⬅️ Назад', callback_data='back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
