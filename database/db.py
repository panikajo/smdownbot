import aiosqlite
from datetime import date, datetime
from config import config

async def get_db():
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    db = await get_db()
    try:
        today = date.today().isoformat()
        row = await db.execute_fetchall(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, last_reset) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, today)
            )
            await db.commit()
            return {"user_id": user_id, "downloads_today": 0, "daily_limit": config.DAILY_LIMIT, "extra_downloads": 0, "is_banned": 0}
        user = dict(row[0])
        # Reset daily counter if new day
        if user["last_reset"] != today:
            await db.execute(
                "UPDATE users SET downloads_today = 0, last_reset = ? WHERE user_id = ?",
                (today, user_id)
            )
            await db.commit()
            user["downloads_today"] = 0
        return user
    finally:
        await db.close()

async def can_download(user_id: int) -> tuple[bool, str]:
    user = await get_or_create_user(user_id)
    if user["is_banned"]:
        return False, "🚫 You are banned."
    limit = user["daily_limit"] or config.DAILY_LIMIT
    if user["daily_limit"] == 0:  # 0 = unlimited
        return True, ""
    used = user["downloads_today"]
    extra = user["extra_downloads"]
    remaining = limit - used + extra
    if remaining <= 0:
        return False, f"📭 Daily limit reached ({limit}/day).\n\n⭐ Buy {config.STARS_EXTRA_DOWNLOADS} extra downloads for {config.STARS_PRICE} Stars — /buy"
    return True, ""

async def record_download(user_id: int, url: str, platform: str, title: str = None, file_size: int = 0):
    db = await get_db()
    try:
        today = date.today().isoformat()
        await db.execute(
            "INSERT INTO downloads (user_id, url, platform, title, file_size) VALUES (?, ?, ?, ?, ?)",
            (user_id, url, platform, title, file_size)
        )

        # Check if user is over daily limit — use extra download instead
        user = await db.execute_fetchall("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if user:
            u = dict(user[0])
            daily_limit = u["daily_limit"] or config.DAILY_LIMIT
            if daily_limit > 0 and u["downloads_today"] >= daily_limit and u["extra_downloads"] > 0:
                # Use extra download
                await db.execute(
                    "UPDATE users SET extra_downloads = MAX(0, extra_downloads - 1) WHERE user_id = ?",
                    (user_id,)
                )
            else:
                # Normal daily counter
                await db.execute(
                    "UPDATE users SET downloads_today = downloads_today + 1 WHERE user_id = ?",
                    (user_id,)
                )

        # Update daily stats
        await db.execute(
            """INSERT INTO stats (date, total_downloads, by_platform)
               VALUES (?, 1, ?)
               ON CONFLICT(date) DO UPDATE SET
               total_downloads = total_downloads + 1,
               by_platform = json_set(by_platform, '$.' || ?, COALESCE(json_extract(by_platform, '$.' || ?), 0) + 1)""",
            (today, f'{{"{platform}": 1}}', platform, platform)
        )
        await db.commit()
    finally:
        await db.close()

async def add_extra_downloads(user_id: int, count: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET extra_downloads = extra_downloads + ? WHERE user_id = ?",
            (count, user_id)
        )
        await db.commit()
    finally:
        await db.close()

async def use_extra_download(user_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET extra_downloads = MAX(0, extra_downloads - 1) WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
    finally:
        await db.close()

async def get_stats():
    db = await get_db()
    try:
        today = date.today().isoformat()
        total_users = await db.execute_fetchall("SELECT COUNT(*) FROM users")
        today_downloads = await db.execute_fetchall(
            "SELECT COUNT(*) FROM downloads WHERE date(created_at) = ?", (today,)
        )
        total_downloads = await db.execute_fetchall("SELECT COUNT(*) FROM downloads")
        return {
            "total_users": total_users[0][0],
            "today_downloads": today_downloads[0][0],
            "total_downloads": total_downloads[0][0],
        }
    finally:
        await db.close()

async def ban_user(user_id: int, ban: bool = True):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if ban else 0, user_id))
        await db.commit()
    finally:
        await db.close()

async def get_all_users():
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM users ORDER BY created_at DESC")
        return [dict(r) for r in rows]
    finally:
        await db.close()

async def get_recent_downloads(limit: int = 50):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM downloads ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()

async def get_user_by_id(user_id: int):
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(rows[0]) if rows else None
    finally:
        await db.close()

async def set_user_limit(user_id: int, limit: int):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET daily_limit = ? WHERE user_id = ?", (limit, user_id))
        await db.commit()
    finally:
        await db.close()

async def get_daily_stats(days: int = 7):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT date, total_downloads FROM stats ORDER BY date DESC LIMIT ?", (days,)
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()

# ─── Bot settings (admin feature toggles) ───────────────────
async def get_setting(key: str, default: str = "1") -> str:
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT value FROM bot_settings WHERE key = ?", (key,))
        return rows[0][0] if rows else default
    finally:
        await db.close()

async def get_all_settings() -> dict:
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT key, value FROM bot_settings")
        return {r[0]: r[1] for r in rows}
    finally:
        await db.close()

async def set_setting(key: str, value: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value)
        )
        await db.commit()
    finally:
        await db.close()

async def toggle_setting(key: str) -> str:
    current = await get_setting(key)
    new = "0" if current == "1" else "1"
    await set_setting(key, new)
    return new

# ─── User language ──────────────────────────────────────────
async def get_user_language(user_id: int) -> str:
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT language FROM users WHERE user_id = ?", (user_id,))
        if rows and rows[0][0]:
            return rows[0][0]
        return "en"
    finally:
        await db.close()

async def set_user_language(user_id: int, lang: str):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()
    finally:
        await db.close()
