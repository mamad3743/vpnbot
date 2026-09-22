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

    trial_days = await settings.get_int("TRIAL_DAYS", 1)
    trial_gb = await settings.get_int("TRIAL_GB", 1)

    try:
        username = f"trial_{user_id}"
        panel_username, sub_link = await panel.create_vpn_user(
            username=username,
            days=trial_days,
            gb=trial_gb,
            note=f"trial:{user_id}",
        )
    except Exception as exc:
        raise TrialError(f"مشکلی در ساخت اکانت تست پیش اومد.\nجزئیات فنی: {exc}")

    await db.mark_trial_used(user_id)
    return {
        "panel_username": panel_username,
        "sub_link": sub_link,
        "trial_days": trial_days,
        "trial_gb": trial_gb,
    }


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
        f"⏳ اعتبار: {result['trial_days']} روز | 📶 حجم: {result['trial_gb']} گیگابایت"
    )
