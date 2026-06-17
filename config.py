import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()  # read variables from a .env file in the project root
except ImportError:
    pass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "519613720"))
    DB_PATH: str = os.getenv("DB_PATH", "data/smdown.db")
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "downloads")
    MAX_FILE_SIZE: int = 50 * 1024 * 1024       # 50MB Telegram bot limit
    PREMIUM_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB for premium
    DAILY_LIMIT: int = int(os.getenv("DAILY_LIMIT", "20"))
    STARS_EXTRA_DOWNLOADS: int = 10
    STARS_PRICE: int = 50  # Stars per extra pack
    STARS_AUDIO: int = 2   # Stars for audio download
    STARS_720P: int = 3    # Stars for 720p download
    STARS_1080P: int = 5   # Stars for 1080p download
    STARS_4K: int = 10     # Stars for 4K/best quality download
    YT_DLP_TIMEOUT: int = 300  # 5 min max per download
    COOKIES_DIR: str = "cookies"

config = Config()
