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
        if 'active_profile_id' not in cols: await db.execute("ALTER TABLE users ADD COLUMN active_profile_id INTEGER")
        await db.execute('''CREATE TABLE IF NOT EXISTS user_photos(
            user_id INTEGER PRIMARY KEY,
            photo BLOB NOT NULL,
            mime TEXT DEFAULT 'image/jpeg',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS user_voice_clones(
            user_id INTEGER PRIMARY KEY,
            voice_id TEXT,
            voice_name TEXT,
            consent INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS person_profiles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            voice_id TEXT,
            photo BLOB,
            mime TEXT DEFAULT 'image/jpeg',
            consent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_person_profiles_user ON person_profiles(user_id)')

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


async def set_photo_bytes(user_id, data: bytes, mime='image/jpeg'):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_photos(user_id,photo,mime,updated_at)
               VALUES(?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
               photo=excluded.photo,mime=excluded.mime,updated_at=CURRENT_TIMESTAMP""",
            (user_id, data, mime or 'image/jpeg')
        )
        await db.execute('UPDATE users SET photo_file_id=NULL WHERE user_id=?', (user_id,))
        await db.commit()

async def get_photo_bytes(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            'SELECT photo,mime FROM user_photos WHERE user_id=?', (user_id,)
        )).fetchone()
    if not row:
        return None, None
    return bytes(row[0]), (row[1] or 'image/jpeg')

async def has_private_photo(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            'SELECT 1 FROM user_photos WHERE user_id=?', (user_id,)
        )).fetchone()
    return bool(row)

async def set_voice_clone(user_id, voice_id, voice_name='FaceTalk Voice', consent=True):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_voice_clones(user_id,voice_id,voice_name,consent,updated_at)
               VALUES(?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
               voice_id=excluded.voice_id,voice_name=excluded.voice_name,
               consent=excluded.consent,updated_at=CURRENT_TIMESTAMP""",
            (user_id, voice_id, voice_name, 1 if consent else 0)
        )
        await db.commit()

async def get_voice_clone(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            'SELECT voice_id,voice_name,consent FROM user_voice_clones WHERE user_id=?',
            (user_id,)
        )).fetchone()
    if not row:
        return None
    return {'voice_id': row[0], 'voice_name': row[1], 'consent': bool(row[2])}

async def delete_voice_clone(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM user_voice_clones WHERE user_id=?', (user_id,))
        await db.commit()


async def ensure_legacy_profile(user_id):
    """Migrate the old single voice/photo into one named profile once, preserving existing installs."""
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await (await db.execute('SELECT id FROM person_profiles WHERE user_id=? LIMIT 1',(user_id,))).fetchone()
        if existing:
            active = await (await db.execute('SELECT active_profile_id FROM users WHERE user_id=?',(user_id,))).fetchone()
            if not active or not active[0]:
                await db.execute('UPDATE users SET active_profile_id=? WHERE user_id=?',(existing[0],user_id)); await db.commit()
            return
        clone = await (await db.execute('SELECT voice_id,voice_name,consent FROM user_voice_clones WHERE user_id=?',(user_id,))).fetchone()
        photo = await (await db.execute('SELECT photo,mime FROM user_photos WHERE user_id=?',(user_id,))).fetchone()
        if clone or photo:
            name = (clone[1] if clone and clone[1] else 'Мой голос')
            cur = await db.execute('''INSERT INTO person_profiles(user_id,name,voice_id,photo,mime,consent)
                                      VALUES(?,?,?,?,?,?)''',(
                user_id,name,(clone[0] if clone else None),(photo[0] if photo else None),
                (photo[1] if photo else 'image/jpeg'),(clone[2] if clone else 0)
            ))
            pid=cur.lastrowid
            await db.execute('UPDATE users SET active_profile_id=? WHERE user_id=?',(pid,user_id)); await db.commit()

async def list_person_profiles(user_id):
    await ensure_legacy_profile(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        active = await (await db.execute('SELECT active_profile_id FROM users WHERE user_id=?',(user_id,))).fetchone()
        rows = await (await db.execute('''SELECT id,name,voice_id,photo IS NOT NULL,updated_at
                                         FROM person_profiles WHERE user_id=? ORDER BY id DESC''',(user_id,))).fetchall()
    aid = int(active[0]) if active and active[0] else None
    return [{'id':int(r[0]),'name':r[1],'has_voice':bool(r[2]),'has_photo':bool(r[3]),'active':int(r[0])==aid,'updated_at':r[4]} for r in rows]

async def create_person_profile(user_id, name, voice_id=None, consent=True):
    await ensure_user(user_id)
    name=(name or 'Новый голос').strip()[:60] or 'Новый голос'
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute('''INSERT INTO person_profiles(user_id,name,voice_id,consent,updated_at)
                                VALUES(?,?,?,?,CURRENT_TIMESTAMP)''',(user_id,name,voice_id,1 if consent else 0))
        pid=cur.lastrowid
        await db.execute('UPDATE users SET active_profile_id=? WHERE user_id=?',(pid,user_id)); await db.commit()
    return pid

async def rename_person_profile(user_id, profile_id, name):
    name=(name or '').strip()[:60]
    if not name: return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute('UPDATE person_profiles SET name=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(name,profile_id,user_id)); await db.commit()
        return cur.rowcount>0

async def select_person_profile(user_id, profile_id):
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT id FROM person_profiles WHERE id=? AND user_id=?',(profile_id,user_id))).fetchone()
        if not row: return False
        await db.execute('UPDATE users SET active_profile_id=? WHERE user_id=?',(profile_id,user_id)); await db.commit(); return True

async def get_active_person_profile(user_id):
    await ensure_legacy_profile(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('''SELECT p.id,p.name,p.voice_id,p.photo,p.mime,p.consent
                                      FROM users u LEFT JOIN person_profiles p ON p.id=u.active_profile_id AND p.user_id=u.user_id
                                      WHERE u.user_id=?''',(user_id,))).fetchone()
    if not row or row[0] is None: return None
    return {'id':int(row[0]),'name':row[1],'voice_id':row[2],'photo':bytes(row[3]) if row[3] is not None else None,'mime':row[4] or 'image/jpeg','consent':bool(row[5])}

async def set_person_profile_photo(user_id, profile_id, data, mime='image/jpeg'):
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute('''UPDATE person_profiles SET photo=?,mime=?,updated_at=CURRENT_TIMESTAMP
                                WHERE id=? AND user_id=?''',(data,mime or 'image/jpeg',profile_id,user_id)); await db.commit(); return cur.rowcount>0

async def get_person_profile_photo(user_id, profile_id):
    async with aiosqlite.connect(DB_PATH) as db:
        row=await (await db.execute('SELECT photo,mime FROM person_profiles WHERE id=? AND user_id=?',(profile_id,user_id))).fetchone()
    if not row or row[0] is None: return None,None
    return bytes(row[0]), row[1] or 'image/jpeg'

async def delete_person_profile(user_id, profile_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur=await db.execute('DELETE FROM person_profiles WHERE id=? AND user_id=?',(profile_id,user_id))
        if cur.rowcount:
            active=await (await db.execute('SELECT active_profile_id FROM users WHERE user_id=?',(user_id,))).fetchone()
            if active and active[0] == profile_id:
                nxt=await (await db.execute('SELECT id FROM person_profiles WHERE user_id=? ORDER BY id DESC LIMIT 1',(user_id,))).fetchone()
                await db.execute('UPDATE users SET active_profile_id=? WHERE user_id=?',((nxt[0] if nxt else None),user_id))
        await db.commit(); return cur.rowcount>0


async def get_setting(key, default=""):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute('SELECT value FROM settings WHERE key=?', (str(key),))).fetchone()
    return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (str(key), str(value))
        )
        await db.commit()
    return value
