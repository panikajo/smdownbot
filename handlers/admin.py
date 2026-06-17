from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db import (
    get_stats, ban_user, get_or_create_user, get_all_users,
    get_recent_downloads, get_user_by_id, set_user_limit, get_daily_stats,
    get_all_settings, toggle_setting, get_user_language,
)
from services.i18n_admin import ta
from config import config

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


async def _lang(uid: int) -> str:
    return await get_user_language(uid)


# ─── Main Admin Panel ───────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    lang = await _lang(message.from_user.id)
    stats = await get_stats()
    text = ta(lang, "dashboard", users=stats["total_users"],
              today=stats["today_downloads"], total=stats["total_downloads"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ta(lang, "btn_users"), callback_data="adm:users:0"),
            InlineKeyboardButton(text=ta(lang, "btn_downloads"), callback_data="adm:dl:0"),
        ],
        [
            InlineKeyboardButton(text=ta(lang, "btn_stats"), callback_data="adm:stats"),
            InlineKeyboardButton(text=ta(lang, "btn_broadcast"), callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton(text=ta(lang, "btn_find"), callback_data="adm:find"),
            InlineKeyboardButton(text=ta(lang, "btn_settings"), callback_data="adm:settings"),
        ],
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ─── Callback Router ────────────────────────────────────────
@router.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        lang = await _lang(callback.from_user.id)
        await callback.answer(ta(lang, "not_authorized"), show_alert=True)
        return

    lang = await _lang(callback.from_user.id)
    parts = callback.data.split(":")
    action = parts[1]

    if action == "users":
        await show_users(callback, lang, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "dl":
        await show_downloads(callback, lang, int(parts[2]) if len(parts) > 2 else 0)
    elif action == "stats":
        await show_stats(callback, lang)
    elif action == "ban":
        await toggle_ban(callback, lang, int(parts[2]), True)
    elif action == "unban":
        await toggle_ban(callback, lang, int(parts[2]), False)
    elif action == "limit":
        await show_limit_menu(callback, lang, int(parts[2]))
    elif action == "setlimit":
        await set_limit(callback, lang, int(parts[2]), int(parts[3]))
    elif action == "userinfo":
        await show_user_info(callback, lang, int(parts[2]))
    elif action == "find":
        await callback.answer(ta(lang, "find_hint"), show_alert=True)
    elif action == "settings":
        await show_settings(callback, lang)
    elif action == "toggle":
        await toggle_feature(callback, lang, parts[2])
    elif action == "gmode":
        await cycle_group_mode(callback, lang)
    elif action == "broadcast":
        await callback.answer(ta(lang, "bc_hint"), show_alert=True)
    elif action == "back":
        await callback.message.delete()
        await cmd_admin(callback.message)
    await callback.answer()


# ─── Users List ─────────────────────────────────────────────
async def show_users(callback: CallbackQuery, lang: str, page: int = 0):
    users = await get_all_users()
    per_page = 8
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    chunk = users[start:start + per_page]

    lines = [ta(lang, "users_title") + "\n"]
    suffix = ta(lang, "today_suffix")
    for u in chunk:
        ban_icon = "\U0001F6AB" if u["is_banned"] else "\u2705"
        name = u["first_name"] or u["username"] or str(u["user_id"])
        lines.append(f"{ban_icon} <code>{u['user_id']}</code> \u2014 {name} ({u['downloads_today']} {suffix})")

    text = "\n".join(lines) + "\n\n" + ta(lang, "page_users", page=page + 1, total=total_pages, count=len(users))
    kb = user_buttons(chunk, page, total_pages, "users", lang)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ─── Recent Downloads ───────────────────────────────────────
async def show_downloads(callback: CallbackQuery, lang: str, page: int = 0):
    downloads = await get_recent_downloads(50)
    per_page = 6
    total_pages = max(1, (len(downloads) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    chunk = downloads[start:start + per_page]

    lines = [ta(lang, "downloads_title") + "\n"]
    for d in chunk:
        icon = {"youtube": "\U0001F534", "instagram": "\U0001F4F8", "tiktok": "\U0001F3B5"}.get(d["platform"], "\U0001F310")
        title = (d["title"] or "")[:35]
        size = f"{d['file_size'] / 1024 / 1024:.1f}MB" if d["file_size"] else "N/A"
        lines.append(f"{icon} <code>{d['user_id']}</code> \u2014 {title} ({size})")

    text = "\n".join(lines) + "\n\n" + ta(lang, "page", page=page + 1, total=total_pages)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="\u25C0\uFE0F", callback_data=f"adm:dl:{page-1}"))
    buttons.append(InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data="adm:back"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="\u25B6\uFE0F", callback_data=f"adm:dl:{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ─── Stats ──────────────────────────────────────────────────
async def show_stats(callback: CallbackQuery, lang: str):
    stats = await get_stats()
    daily = await get_daily_stats(7)
    text = ta(lang, "stats_title", users=stats["total_users"],
              total=stats["total_downloads"], today=stats["today_downloads"])
    if daily:
        text += "\n" + ta(lang, "last7") + "\n"
        for day in daily:
            text += f"  {day['date']}: {day['total_downloads']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data="adm:back")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ─── User Info ──────────────────────────────────────────────
def _user_info_text(lang: str, user: dict, title_key: str) -> str:
    ban_status = ta(lang, "st_banned") if user["is_banned"] else ta(lang, "st_active")
    limit = user["daily_limit"] if user["daily_limit"] != 0 else ta(lang, "unlimited")
    return (
        ta(lang, title_key) + "\n\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"{ta(lang, 'f_name')}: {user['first_name'] or 'N/A'}\n"
        f"{ta(lang, 'f_username')}: @{user['username'] or 'N/A'}\n"
        f"{ta(lang, 'f_status')}: {ban_status}\n"
        f"{ta(lang, 'f_today')}: {user['downloads_today']}\n"
        f"{ta(lang, 'f_limit')}: {limit}\n"
        f"{ta(lang, 'f_extra')}: {user['extra_downloads']}\n"
    )


def _user_action_kb(lang: str, user: dict, back_cb: str) -> InlineKeyboardMarkup:
    uid = user["user_id"]
    ban_text = ta(lang, "btn_unban") if user["is_banned"] else ta(lang, "btn_ban")
    ban_action = f"adm:unban:{uid}" if user["is_banned"] else f"adm:ban:{uid}"
    rows = [[
        InlineKeyboardButton(text=ban_text, callback_data=ban_action),
        InlineKeyboardButton(text=ta(lang, "btn_setlimit"), callback_data=f"adm:limit:{uid}"),
    ]]
    if back_cb:
        rows.append([InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_user_info(callback: CallbackQuery, lang: str, user_id: int):
    user = await get_user_by_id(user_id)
    if not user:
        await callback.answer(ta(lang, "user_not_found"), show_alert=True)
        return
    text = _user_info_text(lang, user, "userinfo_title") + f"{ta(lang, 'f_joined')}: {user['created_at']}\n"
    kb = _user_action_kb(lang, user, "adm:users:0")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ─── Ban/Unban ──────────────────────────────────────────────
async def toggle_ban(callback: CallbackQuery, lang: str, user_id: int, ban: bool):
    await ban_user(user_id, ban)
    toast = ta(lang, "banned_toast", id=user_id) if ban else ta(lang, "unbanned_toast", id=user_id)
    await callback.answer(toast)
    await show_user_info(callback, lang, user_id)


# ─── Limit Menu ─────────────────────────────────────────────
async def show_limit_menu(callback: CallbackQuery, lang: str, user_id: int):
    text = ta(lang, "limit_menu", id=user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10", callback_data=f"adm:setlimit:{user_id}:10"),
            InlineKeyboardButton(text="20", callback_data=f"adm:setlimit:{user_id}:20"),
            InlineKeyboardButton(text="50", callback_data=f"adm:setlimit:{user_id}:50"),
        ],
        [
            InlineKeyboardButton(text="100", callback_data=f"adm:setlimit:{user_id}:100"),
            InlineKeyboardButton(text="\u221E", callback_data=f"adm:setlimit:{user_id}:0"),
        ],
        [InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data=f"adm:userinfo:{user_id}")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


async def set_limit(callback: CallbackQuery, lang: str, user_id: int, limit: int):
    await set_user_limit(user_id, limit)
    label = ta(lang, "unlimited") if limit == 0 else ta(lang, "per_day", n=limit)
    await callback.answer(ta(lang, "limit_set", label=label))
    await show_user_info(callback, lang, user_id)


# ─── Helper: User action buttons ────────────────────────────
def user_buttons(users, page, total_pages, prefix, lang):
    rows = []
    for u in users:
        name = u["first_name"] or u["username"] or str(u["user_id"])[:8]
        rows.append([InlineKeyboardButton(
            text=f"\U0001F464 {name}",
            callback_data=f"adm:userinfo:{u['user_id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u25C0\uFE0F", callback_data=f"adm:{prefix}:{page-1}"))
    nav.append(InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data="adm:back"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="\u25B6\uFE0F", callback_data=f"adm:{prefix}:{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Settings (feature toggles) ─────────────────────────────
SETTING_KEYS = {
    "feature_youtube": "set_youtube",
    "feature_instagram": "set_instagram",
    "feature_tiktok": "set_tiktok",
    "feature_stars": "set_stars",
    "feature_bulk_stories": "set_bulk",
    "feature_language_select": "set_lang",
    "feature_group_buttons": "set_group_buttons",
    "feature_show_tags": "set_show_tags",
    "feature_show_source_channel": "set_show_source_channel",
}


async def show_settings(callback: CallbackQuery, lang: str):
    settings = await get_all_settings()
    text = ta(lang, "settings_title")
    rows = []
    for key, label_key in SETTING_KEYS.items():
        on = settings.get(key, "1") == "1"
        state = ta(lang, "on") if on else ta(lang, "off")
        rows.append([InlineKeyboardButton(
            text=f"{ta(lang, label_key)} \u2014 {state}",
            callback_data=f"adm:toggle:{key}",
        )])
    # 3-state cyclic setting: what to do with links in groups/channels
    mode = settings.get("group_download_mode", "ask")
    mode_label = ta(lang, {
        "ask": "gmode_ask",
        "video": "gmode_video",
        "audio": "gmode_audio",
    }.get(mode, "gmode_ask"))
    rows.append([InlineKeyboardButton(
        text=f"{ta(lang, 'set_group_mode')}: {mode_label}",
        callback_data="adm:gmode",
    )])
    rows.append([InlineKeyboardButton(text=ta(lang, "btn_back"), callback_data="adm:back")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


async def cycle_group_mode(callback: CallbackQuery, lang: str):
    """Cycle the group/channel download mode: ask -> video -> audio -> ask."""
    from database.db import get_setting, set_setting
    cur = await get_setting("group_download_mode", "ask")
    order = ["ask", "video", "audio"]
    try:
        nxt = order[(order.index(cur) + 1) % len(order)]
    except ValueError:
        nxt = "ask"
    await set_setting("group_download_mode", nxt)
    label = ta(lang, {"ask": "gmode_ask", "video": "gmode_video", "audio": "gmode_audio"}[nxt])
    await callback.answer(f"{ta(lang, 'set_group_mode')}: {label}")
    await show_settings(callback, lang)


async def toggle_feature(callback: CallbackQuery, lang: str, key: str):
    if key not in SETTING_KEYS:
        await callback.answer(ta(lang, "unknown_setting"), show_alert=True)
        return
    new = await toggle_setting(key)
    state = ta(lang, "on") if new == "1" else ta(lang, "off")
    await callback.answer(f"{ta(lang, SETTING_KEYS[key])}: {state}")
    await show_settings(callback, lang)


# ─── /find command ──────────────────────────────────────────
@router.message(Command("find"))
async def cmd_find(message: Message):
    if not is_admin(message.from_user.id):
        return
    lang = await _lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(ta(lang, "find_usage"))
        return
    query = parts[1].strip().lstrip("@")
    try:
        user_id = int(query)
        user = await get_user_by_id(user_id)
    except ValueError:
        await message.answer(ta(lang, "find_numeric"))
        return
    if not user:
        await message.answer(ta(lang, "user_not_found"))
        return
    text = _user_info_text(lang, user, "userfound_title")
    kb = _user_action_kb(lang, user, "")
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ─── /broadcast command ─────────────────────────────────────
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    lang = await _lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(ta(lang, "bc_usage"))
        return
    text = parts[1]
    users = await get_all_users()
    sent, failed = 0, 0
    status_msg = await message.answer(ta(lang, "bc_progress", n=len(users)))
    for u in users:
        try:
            await message.bot.send_message(u["user_id"], text)
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(ta(lang, "bc_done", sent=sent, failed=failed))


# ─── /refreshcookies command ─────────────────────────────────
@router.message(Command("refreshcookies"))
async def cmd_refresh_cookies(message: Message):
    if not is_admin(message.from_user.id):
        return
    status = await message.answer("\U0001F504 Refreshing Instagram cookies...")
    from services.cookies import refresh_cookies
    success = await refresh_cookies()
    if success:
        await status.edit_text("\u2705 Instagram cookies refreshed successfully!")
    else:
        await status.edit_text("\u274C Cookie refresh failed. Check logs.")
