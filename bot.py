#!/usr/bin/env python3
import asyncio
import logging
import os
import shutil
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from database.models import init_db
from handlers import start, download, admin, stars
from services.i18n import t, LANGUAGES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("smdownbot")


def check_dependencies():
    """Warn (don't crash) if external tools needed for downloads are missing."""
    # ffmpeg / ffprobe — needed to merge video+audio and split large files
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        logger.warning(
            "ffmpeg/ffprobe not found in PATH. Video+audio merging and "
            "splitting large files will NOT work. Install ffmpeg: "
            "https://ffmpeg.org/download.html"
        )
    else:
        logger.info("ffmpeg/ffprobe found.")

    # Deno (or another JS runtime) — needed by yt-dlp to solve TikTok/YouTube JS challenges
    js_runtime = (
        shutil.which("deno")
        or shutil.which("node")
        or shutil.which("bun")
    )
    if not js_runtime:
        logger.warning(
            "No JavaScript runtime (deno/node/bun) found in PATH. TikTok and "
            "some YouTube downloads will FAIL with 'Unable to extract universal "
            "data for rehydration'. Install Deno (recommended): "
            "https://deno.land/  (Windows: irm https://deno.land/install.ps1 | iex)"
        )
    else:
        logger.info("JavaScript runtime found: %s", js_runtime)


async def set_bot_commands(bot: Bot):
    """Register the Telegram command menu (the '/' menu) per language.
    Public commands go to everyone; admin commands only to the admin chat."""
    from aiogram.types import (
        BotCommand, BotCommandScopeDefault, BotCommandScopeChat,
    )

    def public_cmds(lang):
        return [
            BotCommand(command="start", description=t(lang, "cmd_start")),
            BotCommand(command="help", description=t(lang, "cmd_help")),
            BotCommand(command="stats", description=t(lang, "cmd_stats")),
            BotCommand(command="buy", description=t(lang, "cmd_buy")),
            BotCommand(command="language", description=t(lang, "cmd_language")),
            BotCommand(command="cancel", description=t(lang, "cmd_cancel")),
        ]

    # Public menu — default (English) + per-language
    await bot.set_my_commands(public_cmds("en"), scope=BotCommandScopeDefault())
    for code in LANGUAGES:
        try:
            await bot.set_my_commands(public_cmds(code), language_code=code)
        except Exception as e:
            logger.warning("set_my_commands failed for %s: %s", code, e)

    # Admin-only menu — visible ONLY in the admin's private chat (scope by chat_id)
    if config.ADMIN_ID:
        admin_cmds = public_cmds("en") + [
            BotCommand(command="admin", description="Admin panel"),
            BotCommand(command="find", description="Find a user by ID"),
            BotCommand(command="broadcast", description="Broadcast a message"),
            BotCommand(command="refreshcookies", description="Refresh Instagram cookies"),
        ]
        try:
            await bot.set_my_commands(
                admin_cmds, scope=BotCommandScopeChat(chat_id=config.ADMIN_ID)
            )
        except Exception as e:
            logger.warning("set admin commands failed: %s", e)


async def on_startup(bot: Bot):
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(config.COOKIES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    await init_db(config.DB_PATH)
    # Clear any leftover files from a previous run (junk cleanup)
    try:
        from services.downloader import cleanup_old_files
        cleanup_old_files(max_age_hours=0)
    except Exception as e:
        logger.warning("Startup cleanup failed: %s", e)
    # Register the / command menu so users see what the bot can do
    await set_bot_commands(bot)
    # Remove any active webhook so getUpdates polling can run
    # (fixes TelegramConflictError: can't use getUpdates while webhook is active)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started. DB initialized. Commands set. Webhook cleared.")

async def main():
    check_dependencies()
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_routers(
        stars.router,   # Stars payment handlers first
        start.router,
        download.router,
        admin.router,
    )

    dp.startup.register(on_startup)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query"])

if __name__ == "__main__":
    asyncio.run(main())
