import asyncio
import os
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from database.db import (
    can_download, record_download, use_extra_download,
    get_setting, get_user_language,
)
from services.platform import detect_platform, get_platform_info
from services.downloader import download, get_info, cleanup_file, DownloadResult
from services.limiter import is_downloading, set_active, clear_active, cancel_download
from keyboards.inline import quality_keyboard, cancel_keyboard
from config import config
from services.url_store import store_url, get_url
from services.bulk_stories import get_stories_list
from services.i18n import t

router = Router()


# Bot username used in the "Via" credit line. Override via env if needed.
BOT_USERNAME = os.getenv("BOT_USERNAME", "tikloadtokbot")
VIA_START_PARAM = os.getenv("VIA_START_PARAM", "c")


def _platform_label(platform: str) -> str:
    return {
        "youtube": "YouTube",
        "instagram": "Instagram",
        "tiktok": "TikTok",
    }.get(platform, "Джерело")


def build_caption(result, via_user=None, show_tags=False, show_source_channel=False) -> str:
    """Build the Telegram HTML caption for a finished download.

    Layout:
        🎬 Джерело (<source link>) ✦ Via (<bot link>)
        <blockquote>@uploader_id
        #tag1 #tag2 ...</blockquote>
    The video description / title is intentionally NOT included.
    """
    source_url = result.source_url or ""

    # "Via" points to the user who sent the link.
    # Prefer a public @username link; fall back to a tg://user?id deep link
    # (works for users without a username), else to the bot itself.
    via_url = None
    via_text = "Via"
    if via_user is not None:
        uname = getattr(via_user, "username", None)
        uid = getattr(via_user, "id", None)
        if uname:
            via_url = f"https://t.me/{uname}"
        elif uid:
            via_url = f"tg://user?id={uid}"
    if not via_url:
        via_url = f"https://t.me/{BOT_USERNAME}?start={VIA_START_PARAM}"

    # Line 1: source + via credits
    line1 = f"🎬 <a href=\"{html.escape(source_url, quote=True)}\">Джерело</a> ✦ <a href=\"{html.escape(via_url, quote=True)}\">{html.escape(via_text)}</a>"

    # blockquote block: @login + hashtags (each gated by an admin setting)
    quote_lines = []
    login = result.uploader_id
    if show_source_channel and login:
        login = login.lstrip("@")
        quote_lines.append(f"@{html.escape(login)}")
    tags = result.tags or []
    if show_tags and tags:
        tag_str = " ".join("#" + html.escape(str(t).lstrip("#")) for t in tags if t)
        if tag_str:
            quote_lines.append(tag_str)

    caption = line1
    if quote_lines:
        caption += "\n<blockquote>" + "\n".join(quote_lines) + "</blockquote>"
    # Telegram caption hard limit is 1024 chars
    return caption[:1024]


async def _platform_enabled(platform: str) -> bool:
    key = {
        "youtube": "feature_youtube",
        "instagram": "feature_instagram",
        "tiktok": "feature_tiktok",
    }.get(platform)
    if not key:
        return True
    return await get_setting(key, "1") == "1"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


@router.message(F.text.regexp(r"^@[\w.]{1,30}$"))
async def handle_username(message: Message, bot: Bot):
    """Handle @username - fetch all Instagram stories."""
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    username = message.text.strip().lstrip("@")

    if await get_setting("feature_bulk_stories", "1") != "1" or await get_setting("feature_instagram", "1") != "1":
        await message.answer(t(lang, "feature_disabled"))
        return

    ok, err = await can_download(user_id)
    if not ok:
        await message.answer(err)
        return

    url = f"https://www.instagram.com/stories/{username}/"
    await handle_bulk_stories(message, bot, url, user_id)


async def handle_bulk_stories(message: Message, bot: Bot, url: str, user_id: int):
    """Handle bulk story download for instagram.com/stories/username/"""
    lang = await get_user_language(user_id)
    loading = await message.answer(t(lang, "fetching_stories"))

    stories = await get_stories_list(url)
    if not stories:
        await loading.edit_text(t(lang, "no_stories"))
        return

    total = len(stories)
    await loading.edit_text(t(lang, "stories_found", total=total))

    downloaded = 0
    failed = 0

    for story in stories:
        i = story.index
        ok, err = await can_download(user_id)
        if not ok:
            await message.answer(err)
            break

        if is_downloading(user_id) and cancel_download(user_id):
            await message.answer(t(lang, "cancelled"))
            return

        progress_msg = await message.answer(t(lang, "story_progress", i=i, total=total))

        from services.bulk_stories import download_story_by_index
        result = await download_story_by_index(url, i)

        if not result["success"]:
            failed += 1
            err_msg = result["error"][:50] if result["error"] else ""
            await progress_msg.edit_text(t(lang, "dl_failed", error=err_msg))
            continue

        file_path = result["file_path"]
        file_size = result["file_size"]

        if file_size > config.MAX_FILE_SIZE:
            cleanup_file(file_path)
            failed += 1
            await progress_msg.edit_text(t(lang, "too_large", size=format_size(file_size)))
            continue

        try:
            caption = t(lang, "story_progress", i=i, total=total)
            file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=user_id, video=file, caption=caption,
                parse_mode="HTML", supports_streaming=True,
            )
            downloaded += 1
            await record_download(user_id, url, "instagram", result["title"], file_size)
            await progress_msg.delete()
        except Exception as e:
            failed += 1
            await progress_msg.edit_text(t(lang, "upload_failed", error=str(e)[:50]))
        finally:
            cleanup_file(file_path)

    await message.answer(t(lang, "stories_summary", ok=downloaded, total=total))


@router.message(F.text.regexp(r"https?://\S+"))
async def handle_link(message: Message, bot: Bot):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    url = message.text.strip()

    if is_downloading(user_id):
        await message.reply(t(lang, "already_downloading"))
        return

    ok, err = await can_download(user_id)
    if not ok:
        await message.reply(err)
        return

    result = detect_platform(url)
    if not result:
        await message.reply(t(lang, "unrecognized_link"))
        return

    platform, video_id = result
    pinfo = get_platform_info(platform)

    if not await _platform_enabled(platform):
        await message.reply(t(lang, "feature_disabled"))
        return

    if platform == "instagram" and "stories/" in url and not video_id.isdigit():
        await handle_bulk_stories(message, bot, url, user_id)
        return

    # In groups/channels the admin can choose to auto-download instead of
    # showing the inline buttons. In private chats we always show buttons.
    is_group = message.chat.type in ("group", "supergroup", "channel")
    group_mode = await get_setting("group_download_mode", "ask") if is_group else "ask"

    if is_group and group_mode in ("video", "audio"):
        quality = "audio" if group_mode == "audio" else "best"
        loading = await message.reply(t(lang, "analyzing"))
        short_id = store_url(url, platform)
        await process_quality_download(
            bot, user_id, quality, short_id, message.chat.id, loading,
            via_user=message.from_user, reply_to_message_id=message.message_id,
        )
        return

    loading = await message.reply(t(lang, "analyzing"))

    # TikTok: skip the get_info gate (often fails even when download works)
    if platform == "tiktok":
        await loading.edit_text(
            t(lang, "tiktok_choose"),
            parse_mode="HTML",
            reply_markup=quality_keyboard(store_url(url, platform), platform),
        )
        return

    info = await get_info(url, platform)
    if not info:
        if platform == "instagram":
            await loading.edit_text(t(lang, "ig_cant_access"), parse_mode="HTML")
        else:
            await loading.edit_text(t(lang, "cant_fetch"))
        return

    title = info.get("title", "Unknown")[:80]
    title_safe = html.escape(title)
    duration = info.get("duration")
    uploader = info.get("uploader", "")

    text = f"{pinfo.icon} <b>{title_safe}</b>"
    if uploader:
        text += f"\n\U0001F464 {html.escape(uploader)}"
    if duration:
        text += f"\n\u23F1 {format_duration(duration)}"
    if pinfo.note:
        text += f"\n\U0001F4A1 {pinfo.note}"

    await loading.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=quality_keyboard(store_url(url, platform), platform),
    )


@router.callback_query(F.data.startswith("dl:"))
async def process_download(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return
    quality = parts[1]
    short_id = parts[2]
    await callback.answer()
    # Reply the result to the original link message. The buttons message
    # (callback.message) was sent as a reply to that link, so its
    # reply_to_message points back to it.
    orig = callback.message.reply_to_message
    reply_to_id = orig.message_id if orig else None
    await process_quality_download(
        bot, user_id, quality, short_id, callback.message.chat.id, callback.message,
        via_user=callback.from_user, reply_to_message_id=reply_to_id,
    )


async def process_quality_download(bot: Bot, user_id: int, quality: str, short_id: str, chat_id: int, edit_msg=None, via_user=None, reply_to_message_id=None):
    """Download logic shared between regular and premium (Stars-paid) downloads."""
    lang = await get_user_language(user_id)
    audio_only = quality == "audio"

    url_data = get_url(short_id)
    if not url_data:
        msg = t(lang, "link_expired")
        if edit_msg:
            await edit_msg.edit_text(msg)
        else:
            await bot.send_message(chat_id, msg)
        return
    url, platform = url_data

    if quality not in ("audio", "720", "1080", "4k"):
        ok, err = await can_download(user_id)
        if not ok:
            if edit_msg:
                await edit_msg.edit_text(err)
            else:
                await bot.send_message(chat_id, err)
            return

    if edit_msg:
        status_msg = await edit_msg.edit_text(t(lang, "downloading"), parse_mode="HTML")
    else:
        status_msg = await bot.send_message(chat_id, t(lang, "downloading"), parse_mode="HTML")

    async def do_download():
        return await download(url, platform, audio_only=audio_only, quality=quality)

    task = asyncio.create_task(do_download())
    set_active(user_id, task)

    try:
        result = await task
    except asyncio.CancelledError:
        await status_msg.edit_text(t(lang, "cancelled"))
        return
    finally:
        clear_active(user_id)

    if not result.success:
        error_text = result.error[:150] if result.error else "Unknown error"
        await status_msg.edit_text(t(lang, "dl_failed", error=error_text), parse_mode="HTML")
        return

    if result.file_size > config.MAX_FILE_SIZE:
        await status_msg.edit_text(t(lang, "too_large_split", size=format_size(result.file_size)), parse_mode="HTML")
        from services.downloader import split_video
        try:
            parts = await asyncio.get_event_loop().run_in_executor(None, split_video, result.file_path)
        except Exception as e:
            cleanup_file(result.file_path)
            await status_msg.edit_text(t(lang, "split_failed", error=str(e)[:100]), parse_mode="HTML")
            return

        if len(parts) <= 1:
            cleanup_file(result.file_path)
            await status_msg.edit_text(t(lang, "too_large", size=format_size(result.file_size)), parse_mode="HTML")
            return

        await status_msg.edit_text(t(lang, "uploading_parts", count=len(parts)), parse_mode="HTML")
        for i, part_path in enumerate(parts, 1):
            try:
                part_size = os.path.getsize(part_path)
                caption = f"\U0001F3AC <b>{html.escape(result.title or '')}</b>\n\U0001F4E6 {i}/{len(parts)} \u2014 {format_size(part_size)}"
                file = FSInputFile(part_path)
                await bot.send_video(
                    chat_id=chat_id, video=file, caption=caption,
                    parse_mode="HTML", supports_streaming=True,
                    reply_to_message_id=reply_to_message_id if i == 1 else None,
                )
                cleanup_file(part_path)
            except Exception as e:
                await bot.send_message(chat_id, t(lang, "part_failed", i=i, error=str(e)[:50]))
                cleanup_file(part_path)

        await record_download(user_id, url, platform, result.title, result.file_size)
        await status_msg.delete()
        cleanup_file(result.file_path)
        return

    await status_msg.edit_text(t(lang, "uploading"), parse_mode="HTML")

    show_tags = await get_setting("feature_show_tags", "0") == "1"
    show_source_channel = await get_setting("feature_show_source_channel", "0") == "1"

    try:
        caption = build_caption(
            result, via_user=via_user,
            show_tags=show_tags, show_source_channel=show_source_channel,
        )

        file = FSInputFile(result.file_path)
        if audio_only:
            await bot.send_audio(
                chat_id=chat_id, audio=file, caption=caption, parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        else:
            await bot.send_video(
                chat_id=chat_id, video=file, caption=caption,
                parse_mode="HTML", supports_streaming=True,
                reply_to_message_id=reply_to_message_id,
            )

        await record_download(user_id, url, platform, result.title, result.file_size)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(t(lang, "upload_failed", error=str(e)[:100]))
    finally:
        cleanup_file(result.file_path)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    lang = await get_user_language(message.from_user.id)
    if cancel_download(message.from_user.id):
        await message.answer(t(lang, "cancelled"))
    else:
        await message.answer(t(lang, "no_active"))


@router.callback_query(F.data == "cancel")
async def cancel_button(callback: CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    if cancel_download(callback.from_user.id):
        await callback.message.edit_text(t(lang, "cancelled"))
    await callback.answer()
