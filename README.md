# FaceTalk AI Bot v1

Отдельный Telegram-бот: пользователь загружает фото, выбирает роль и общается с AI текстом или голосом.

## Уже работает
- /start и красивое меню
- загрузка/сохранение фотографии Telegram
- роли: Психолог, Тренер, Учитель, Бизнес-консультант, Друг
- память текущего диалога в SQLite
- текстовые ответы OpenAI
- распознавание голосовых
- голосовой ответ TTS
- кнопка «Новый разговор»
- provider-neutral модуль `app/avatar.py` для talking-avatar видео

## Запуск
1. Создайте нового бота в @BotFather и получите token.
2. `cp .env.example .env`
3. Вставьте `TELEGRAM_BOT_TOKEN` и `OPENAI_API_KEY`.
4. `pip install -r requirements.txt`
5. `python run.py`

## Что нужно для настоящего видео-лица
Для реалистичного движения губ нужен внешний talking-avatar API. Он подключается только в `app/avatar.py`; остальной бот менять не нужно.

## Railway
Start command: `python run.py`
Переменные окружения: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` и при необходимости настройки avatar provider.

## Railway FIX v1.1
В эту сборку добавлены `main.py`, `railway.toml`, `Procfile` и `.python-version`.
Railway теперь получает явную команду запуска `python main.py`, поэтому ошибка `No start command detected` устранена на уровне проекта.
