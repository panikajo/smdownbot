from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from database.db import add_extra_downloads, get_or_create_user, get_user_language
from config import config
from services.i18n import t, LANGUAGES

router = Router()

# In-memory store for pending premium downloads
# Key: f"premium_{user_id}", Value: (quality, short_id)
_pending_downloads: dict[str, tuple[str, str]] = {}

QUALITY_PRICES = {
    "audio": config.STARS_AUDIO,
    "720": config.STARS_720P,
    "1080": config.STARS_1080P,
    "4k": config.STARS_4K,
}

QUALITY_LABELS = {
    "audio": "Audio MP3",
    "720": "720p HD",
    "1080": "1080p Full HD",
    "4k": "4K Best Quality",
}


# ─── /buy command ───────────────────────────────────────────
@router.message(Command("buy"))
async def cmd_buy(message: Message):
    if await _buy_disabled(message):
        return
    lang = await get_user_language(message.from_user.id)
    user = await get_or_create_user(message.from_user.id)
    extra = user.get("extra_downloads", 0)

    text = t(lang, "buy_title", extra=extra,
             count=config.STARS_EXTRA_DOWNLOADS, price=config.STARS_PRICE)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t(lang, "buy_btn", count=config.STARS_EXTRA_DOWNLOADS, price=config.STARS_PRICE),
            callback_data="buy_stars"
        )]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def _buy_disabled(message: Message) -> bool:
    """If the Stars feature is off, tell the user and return True."""
    from database.db import get_setting
    if await get_setting("feature_stars", "1") != "1":
        lang = await get_user_language(message.from_user.id)
        await message.answer(t(lang, "feature_disabled"))
        return True
    return False


# ─── Reply-keyboard "Buy extra" button (text in any language) ─
@router.message(F.text.func(lambda txt: txt and any(
    txt == t(code, "btn_buy") for code in LANGUAGES
)))
async def btn_buy(message: Message):
    await cmd_buy(message)


# ─── Buy button callback ────────────────────────────────────
@router.callback_query(F.data == "buy_stars")
async def buy_stars_callback(callback: CallbackQuery, bot: Bot):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Extra Downloads",
        description=f"{config.STARS_EXTRA_DOWNLOADS} extra downloads for today",
        payload=f"extra_downloads_{callback.from_user.id}",
        currency="XTR",  # Telegram Stars currency
        prices=[LabeledPrice(label="Extra Downloads", amount=config.STARS_PRICE)],
    )
    await callback.answer()


# ─── Premium quality callback (pm:quality:short_id) ─────────
@router.callback_query(F.data.startswith("pm:"))
async def premium_quality_callback(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid request")
        return

    quality = parts[1]
    short_id = parts[2]
    price = QUALITY_PRICES.get(quality)
    label = QUALITY_LABELS.get(quality, quality)

    if not price:
        await callback.answer("Unknown quality")
        return

    user_id = callback.from_user.id

    # Store pending download
    _pending_downloads[f"premium_{user_id}"] = (quality, short_id)

    await bot.send_invoice(
        chat_id=user_id,
        title=f"{label} Download",
        description=f"Download video in {label} quality",
        payload=f"premium_{quality}_{user_id}",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=price)],
    )
    await callback.answer()


# ─── Pre-checkout (required by Telegram) ────────────────────
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)


# ─── Successful payment ─────────────────────────────────────
@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    payload = payment.invoice_payload

    if payload.startswith("extra_downloads_"):
        # Extra downloads purchase
        await add_extra_downloads(user_id, config.STARS_EXTRA_DOWNLOADS)
        user = await get_or_create_user(user_id)
        extra = user.get("extra_downloads", 0)
        lang = await get_user_language(user_id)
        await message.answer(
            t(lang, "pay_ok_extra", count=config.STARS_EXTRA_DOWNLOADS,
              paid=payment.total_amount, extra=extra),
            parse_mode="HTML",
        )

    elif payload.startswith("premium_"):
        # Premium quality download — trigger the download automatically
        lang = await get_user_language(user_id)
        pending_key = f"premium_{user_id}"
        pending = _pending_downloads.pop(pending_key, None)

        if not pending:
            await message.answer(
                t(lang, "pay_expired", paid=payment.total_amount),
                parse_mode="HTML",
            )
            return

        quality, short_id = pending
        label = QUALITY_LABELS.get(quality, quality)

        await message.answer(
            t(lang, "pay_ok_premium", label=label, paid=payment.total_amount),
            parse_mode="HTML",
        )

        from handlers.download import process_quality_download
        await process_quality_download(message.bot, user_id, quality, short_id, message.chat.id, via_user=message.from_user)
