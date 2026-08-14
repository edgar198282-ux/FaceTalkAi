import json
import aiosqlite
from datetime import datetime, timezone
from .config import DB_PATH, DEFAULT_VIDEO_DAILY_LIMIT

def _day():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'friend', photo_file_id TEXT,
            history TEXT DEFAULT '[]', reply_mode TEXT DEFAULT 'video',
            video_daily_limit INTEGER
        )''')
        cols = {r[1] for r in await (await db.execute('PRAGMA table_info(users)')).fetchall()}
        if 'reply_mode' not in cols: await db.execute("ALTER TABLE users ADD COLUMN reply_mode TEXT DEFAULT 'video'")
        if 'video_daily_limit' not in cols: await db.execute("ALTER TABLE users ADD COLUMN video_daily_limit INTEGER")
        await db.execute('''CREATE TABLE IF NOT EXISTS usage_daily(
            day TEXT NOT NULL, user_id INTEGER NOT NULL,
            text_requests INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
            tts_chars INTEGER DEFAULT 0, video_attempts INTEGER DEFAULT 0, video_success INTEGER DEFAULT 0,
            PRIMARY KEY(day,user_id)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)''')
        await db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES("video_daily_limit",?)',(str(DEFAULT_VIDEO_DAILY_LIMIT),))
        await db.commit()

async def ensure_user(user_id:int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users(user_id) VALUES(?)',(user_id,)); await db.commit()

async def set_role(user_id, role):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET role=?, history=? WHERE user_id=?',(role,'[]',user_id)); await db.commit()
async def set_photo(user_id,file_id):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET photo_file_id=? WHERE user_id=?',(file_id,user_id)); await db.commit()
async def set_reply_mode(user_id,mode):
    await ensure_user(user_id); mode='video' if mode=='video' else 'voice'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET reply_mode=? WHERE user_id=?',(mode,user_id)); await db.commit()
async def reset_history(user_id):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET history=? WHERE user_id=?',('[]',user_id)); await db.commit()

async def get_global_video_limit():
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT value FROM settings WHERE key="video_daily_limit"')).fetchone()
    try:return max(0,int(row[0]))
    except:return DEFAULT_VIDEO_DAILY_LIMIT
async def set_global_video_limit(n):
    n=max(0,min(100,int(n)))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO settings(key,value) VALUES("video_daily_limit",?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(str(n),)); await db.commit()
    return n

async def get_user(user_id):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT role,photo_file_id,history,COALESCE(reply_mode,"video"),video_daily_limit FROM users WHERE user_id=?',(user_id,))).fetchone()
    limit=row[4] if row[4] is not None else await get_global_video_limit()
    return {'role':row[0],'photo_file_id':row[1],'history':json.loads(row[2] or '[]'),'reply_mode':row[3],'video_daily_limit':int(limit)}

async def append_history(user_id,role,content,max_items=20):
    u=await get_user(user_id); hist=(u['history']+[{'role':role,'content':content}])[-max_items:]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET history=? WHERE user_id=?',(json.dumps(hist,ensure_ascii=False),user_id)); await db.commit()

async def add_usage(user_id, text_requests=0,input_tokens=0,output_tokens=0,tts_chars=0,video_attempts=0,video_success=0):
    day=_day()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO usage_daily(day,user_id,text_requests,input_tokens,output_tokens,tts_chars,video_attempts,video_success)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(day,user_id) DO UPDATE SET
        text_requests=text_requests+excluded.text_requests,input_tokens=input_tokens+excluded.input_tokens,
        output_tokens=output_tokens+excluded.output_tokens,tts_chars=tts_chars+excluded.tts_chars,
        video_attempts=video_attempts+excluded.video_attempts,video_success=video_success+excluded.video_success''',
        (day,user_id,text_requests,input_tokens,output_tokens,tts_chars,video_attempts,video_success)); await db.commit()

async def video_remaining(user_id):
    u=await get_user(user_id); limit=u['video_daily_limit']; day=_day()
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT COALESCE(video_success,0) FROM usage_daily WHERE day=? AND user_id=?',(day,user_id))).fetchone()
    used=int(row[0]) if row else 0
    return {'limit':limit,'used':used,'remaining':max(0,limit-used)}

async def admin_stats():
    day=_day()
    async with aiosqlite.connect(DB_PATH) as db:
        users=(await (await db.execute('SELECT COUNT(*) FROM users')).fetchone())[0]
        row=await (await db.execute('''SELECT COALESCE(SUM(text_requests),0),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(tts_chars),0),COALESCE(SUM(video_attempts),0),COALESCE(SUM(video_success),0) FROM usage_daily WHERE day=?''',(day,))).fetchone()
        allrow=await (await db.execute('''SELECT COALESCE(SUM(text_requests),0),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(tts_chars),0),COALESCE(SUM(video_attempts),0),COALESCE(SUM(video_success),0) FROM usage_daily''')).fetchone()
    return {'day':day,'users':users,'today':row,'all':allrow,'video_limit':await get_global_video_limit()}


async def set_provider_state(provider, state, message=''):
    payload=json.dumps({'state':state,'message':message[:300]},ensure_ascii=False)
    key=f'provider_state:{provider}'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,payload))
        await db.commit()

async def get_provider_state(provider):
    key=f'provider_state:{provider}'
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT value FROM settings WHERE key=?',(key,))).fetchone()
    if not row:
        return {'state':'unknown','message':''}
    try:
        return json.loads(row[0])
    except Exception:
        return {'state':'unknown','message':''}
