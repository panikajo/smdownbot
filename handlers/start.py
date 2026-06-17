from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from database.db import (
    get_or_create_user, get_user_language, set_user_language, get_setting,
)
from services.i18n import t, LANGUAGES
from keyboards.inline import main_menu_keyboard, language_keyboard
from config import config

router = Router()


async def _menu_flags():
    """Read admin toggles that affect the user menu."""
    show_buy = await get_setting("feature_stars", "1") == "1"
    show_lang = await get_setting("feature_language_select", "1") == "1"
    return show_buy, show_lang


async def send_main_menu(message: Message, lang: str):
    # In groups/channels: don't attach the reply keyboard unless the admin
    # explicitly enabled it (feature_group_buttons, default OFF). Instead show
    # a short capabilities intro.
    is_private = message.chat.type == "private"
    if not is_private:
        group_buttons_on = await get_setting("feature_group_buttons", "0") == "1"
        if not group_buttons_on:
            await message.answer(t(lang, "group_intro"), parse_mode="HTML")
            return

    show_buy, show_lang = await _menu_flags()
    is_admin = is_private and message.chat.id == config.ADMIN_ID
    await message.answer(
        t(lang, "welcome"),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(
            lang, show_buy=show_buy, show_language=show_lang, is_admin=is_admin
        ),
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    lang = await get_user_language(message.from_user.id)
    await send_main_menu(message, lang)


async def _buttons_allowed(message: Message) -> bool:
    """Reply-keyboard buttons work in private always; in groups only if enabled."""
    if message.chat.type == "private":
        return True
    return await get_setting("feature_group_buttons", "0") == "1"


# ─── Button: Help ───────────────────────────────────────────
@router.message(F.text.func(lambda txt: txt and any(
    txt == t(code, "btn_help") for code in LANGUAGES
)))
async def btn_help(message: Message):
    if not await _buttons_allowed(message):
        return
    lang = await get_user_language(message.from_user.id)
    await message.answer(t(lang, "help"), parse_mode="HTML")


# ─── Button: My stats ───────────────────────────────────────
@router.message(F.text.func(lambda txt: txt and any(
    txt == t(code, "btn_stats") for code in LANGUAGES
)))
async def btn_stats(message: Message):
    if not await _buttons_allowed(message):
        return
    lang = await get_user_language(message.from_user.id)
    user = await get_or_create_user(message.from_user.id)
    limit = user["daily_limit"] if user["daily_limit"] is not None else config.DAILY_LIMIT
    used = user["downloads_today"]
    extra = user["extra_downloads"]
    remaining = "\u221E" if limit == 0 else str(limit - used + extra)
    limit_disp = "\u221E" if limit == 0 else str(limit)
    await message.answer(
        t(lang, "stats", used=used, limit=limit_disp, extra=extra, remaining=remaining),
        parse_mode="HTML",
    )


# ─── Button: Language ───────────────────────────────────────
@router.message(F.text.func(lambda txt: txt and any(
    txt == t(code, "btn_language") for code in LANGUAGES
)))
async def btn_language(message: Message):
    if not await _buttons_allowed(message):
        return
    if await get_setting("feature_language_select", "1") != "1":
        lang = await get_user_language(message.from_user.id)
        await message.answer(t(lang, "feature_disabled"))
        return
    lang = await get_user_language(message.from_user.id)
    await message.answer(t(lang, "choose_language"), reply_markup=language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def set_language_cb(callback: CallbackQuery):
    code = callback.data.split(":", 1)[1]
    if code not in LANGUAGES:
        await callback.answer()
        return
    await set_user_language(callback.from_user.id, code)
    await callback.answer(t(code, "language_set"))
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_main_menu(callback.message, code)


# ─── Button: Admin (admin only) ─────────────────────────────
@router.message(F.text.func(lambda txt: txt and any(
    txt == t(code, "btn_admin") for code in LANGUAGES
)))
async def btn_admin(message: Message):
    if message.chat.type != "private" or message.from_user.id != config.ADMIN_ID:
        return
    from handlers.admin import cmd_admin
    await cmd_admin(message)


# Keep /help and /stats as fallback commands too
@router.message(Command("help"))
async def cmd_help(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(t(lang, "help"), parse_mode="HTML")


@router.message(Command("language"))
async def cmd_language(message: Message):
    await btn_language(message)
