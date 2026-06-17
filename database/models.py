import aiosqlite
from datetime import datetime, date

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    daily_limit INTEGER DEFAULT 20,
    downloads_today INTEGER DEFAULT 0,
    last_reset TEXT,
    extra_downloads INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    platform TEXT,
    title TEXT,
    file_size INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS stats (
    date TEXT PRIMARY KEY,
    total_downloads INTEGER DEFAULT 0,
    total_users INTEGER DEFAULT 0,
    by_platform TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Settings that can be toggled from the admin panel. Default: all enabled ("1").
DEFAULT_SETTINGS = {
    "feature_youtube": "1",
    "feature_instagram": "1",
    "feature_tiktok": "1",
    "feature_stars": "1",
    "feature_bulk_stories": "1",
    "feature_language_select": "1",
    # Reply-keyboard buttons inside groups/channels — OFF by default
    "feature_group_buttons": "0",
    # Show source hashtags in the video caption — OFF by default
    "feature_show_tags": "0",
    # Show source channel/author login in the caption — OFF by default
    "feature_show_source_channel": "0",
    # In groups/channels: what to do with a link.
    #   "ask"   — show the quality/format buttons (default)
    #   "video" — auto-download video, no buttons
    #   "audio" — auto-download audio, no buttons
    "group_download_mode": "ask",
}


async def init_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(DB_SCHEMA)
        # Migration: add language column to users if missing
        cur = await db.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in await cur.fetchall()]
        if "language" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
        # Seed default settings
        for k, v in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (k, v)
            )
        await db.commit()
