from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from config import config
from services.i18n import t, LANGUAGES


def main_menu_keyboard(lang: str = "en", show_buy: bool = True, show_language: bool = True, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Persistent reply-keyboard menu shown to users (buttons instead of commands)."""
    rows = [[KeyboardButton(text=t(lang, "btn_help")), KeyboardButton(text=t(lang, "btn_stats"))]]
    last = []
    if show_buy:
        last.append(KeyboardButton(text=t(lang, "btn_buy")))
    if show_language:
        last.append(KeyboardButton(text=t(lang, "btn_language")))
    if last:
        rows.append(last)
    # Add group/channel buttons
    rows.append([
        KeyboardButton(text=t(lang, "btn_add_group")),
        KeyboardButton(text=t(lang, "btn_add_channel")),
    ])
    if is_admin:
        rows.append([KeyboardButton(text=t(lang, "btn_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def language_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"lang:{code}")]
            for code, name in LANGUAGES.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quality_keyboard(short_id: str, platform: str) -> InlineKeyboardMarkup:
    buttons = []
    if platform in ("youtube", "unknown"):
        buttons.append([
            InlineKeyboardButton(text="📱 480p (Free)", callback_data=f"dl:480:{short_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🎵 Audio MP3 ⭐2", callback_data=f"pm:audio:{short_id}"),
            InlineKeyboardButton(text="🎬 720p ⭐3", callback_data=f"pm:720:{short_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🔥 1080p ⭐5", callback_data=f"pm:1080:{short_id}"),
            InlineKeyboardButton(text="⭐ 4K Best ⭐10", callback_data=f"pm:4k:{short_id}"),
        ])
    elif platform == "tiktok":
        buttons.append([
            InlineKeyboardButton(text="🎬 Video", callback_data=f"dl:best:{short_id}"),
            InlineKeyboardButton(text="🎵 Audio Only", callback_data=f"dl:audio:{short_id}"),
        ])
    elif platform == "instagram":
        buttons.append([
            InlineKeyboardButton(text="📥 Download", callback_data=f"dl:best:{short_id}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Download", callback_data="cancel")]
    ])


def buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Buy {config.STARS_EXTRA_DOWNLOADS} extra downloads",
            callback_data="buy_stars"
        )]
    ])
