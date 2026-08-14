import json
import aiosqlite
from .config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'friend',
            photo_file_id TEXT,
            history TEXT DEFAULT '[]',
            reply_mode TEXT DEFAULT 'video'
        )''')
        cols = {r[1] for r in await (await db.execute('PRAGMA table_info(users)')).fetchall()}
        if 'reply_mode' not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN reply_mode TEXT DEFAULT 'video'")
        await db.commit()

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users(user_id) VALUES(?)', (user_id,))
        await db.commit()

async def set_role(user_id: int, role: str):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET role=?, history=? WHERE user_id=?', (role, '[]', user_id))
        await db.commit()

async def set_photo(user_id: int, file_id: str):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET photo_file_id=? WHERE user_id=?', (file_id, user_id))
        await db.commit()

async def set_reply_mode(user_id: int, mode: str):
    await ensure_user(user_id)
    mode = 'video' if mode == 'video' else 'voice'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET reply_mode=? WHERE user_id=?', (mode, user_id))
        await db.commit()

async def reset_history(user_id: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET history=? WHERE user_id=?', ('[]', user_id))
        await db.commit()

async def get_user(user_id: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute('SELECT role, photo_file_id, history, COALESCE(reply_mode, "video") FROM users WHERE user_id=?', (user_id,))
        row = await cur.fetchone()
    return {'role': row[0], 'photo_file_id': row[1], 'history': json.loads(row[2] or '[]'), 'reply_mode': row[3]}

async def append_history(user_id: int, role: str, content: str, max_items: int = 20):
    u = await get_user(user_id)
    hist = u['history'] + [{'role': role, 'content': content}]
    hist = hist[-max_items:]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET history=? WHERE user_id=?', (json.dumps(hist, ensure_ascii=False), user_id))
        await db.commit()
