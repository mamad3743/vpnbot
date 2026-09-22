from aiogram import F, Router
from aiogram.types import Message

import database as db
import keyboards as kb
import panel
import settings

router = Router(name="trial")


class TrialError(Exception):
    pass


async def create_trial(user_id: int) -> dict:
    """Shared trial-creation logic, used by the reply-keyboard button and the
    Telegram Mini App (web_app_data) flow."""
    if await db.has_used_trial(user_id):
        raise TrialError("شما قبلا از اکانت تست رایگان استفاده کردی.")

    trial_hours, trial_mb = await get_trial_limits()

    try:
        username = f"trial_{user_id}"
        panel_username, sub_link = await panel.create_vpn_user(
            username=username,
            days=trial_hours / 24,
            gb=trial_mb / 1024,
            note=f"trial:{user_id}",
        )
    except Exception as exc:
        raise TrialError(f"مشکلی در ساخت اکانت تست پیش اومد.\nجزئیات فنی: {exc}")

    await db.mark_trial_used(user_id)
    return {
        "panel_username": panel_username,
        "sub_link": sub_link,
        "trial_hours": trial_hours,
        "trial_mb": trial_mb,
    }


async def get_trial_limits() -> tuple[int, int]:
    """Trial size in (hours, megabytes). Falls back to the old day/GB keys
    so bots configured before this change keep working without re-setup."""
    hours = await settings.get_int("TRIAL_HOURS", 0)
    if hours <= 0:
        old_days = await settings.get_int("TRIAL_DAYS", 0)
        hours = old_days * 24 if old_days > 0 else 24
    mb = await settings.get_int("TRIAL_MB", 0)
    if mb <= 0:
        old_gb = await settings.get_int("TRIAL_GB", 0)
        mb = old_gb * 1024 if old_gb > 0 else 500
    return hours, mb


@router.message(F.text == kb.BTN_TRIAL)
async def get_trial(message: Message):
    await message.answer("⏳ در حال ساخت اکانت تست...")
    try:
        result = await create_trial(message.from_user.id)
    except TrialError as exc:
        await message.answer(f"❌ {exc}")
        return

    await message.answer(
        "🎁 اکانت تست شما ساخته شد!\n\n"
        f"👤 یوزرنیم: <code>{result['panel_username']}</code>\n"
        f"🔗 لینک اشتراک:\n<code>{result['sub_link']}</code>\n\n"
        f"⏳ اعتبار: {result['trial_hours']} ساعت | 📶 حجم: {result['trial_mb']} مگابایت"
    )
