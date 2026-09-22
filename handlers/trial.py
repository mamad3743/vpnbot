from aiogram import F, Router
from aiogram.types import Message

import database as db
import keyboards as kb
import panel
import settings

router = Router(name="trial")


class TrialError(Exception):
    pass


def _format_duration(minutes: int) -> str:
    if minutes % 1440 == 0:
        return f"{minutes // 1440} روز"
    if minutes % 60 == 0:
        return f"{minutes // 60} ساعت"
    return f"{minutes} دقیقه"


def _format_size(mb: int) -> str:
    if mb % 1024 == 0:
        return f"{mb // 1024} گیگابایت"
    return f"{mb} مگابایت"


async def create_trial(user_id: int) -> dict:
    """Shared trial-creation logic, used by the reply-keyboard button and the
    Telegram Mini App (web_app_data) flow. Trial size/duration is stored in
    fine-grained minutes/MB so it can be e.g. "600MB for 1 hour"."""
    if await db.has_used_trial(user_id):
        raise TrialError("شما قبلا از اکانت تست رایگان استفاده کردی.")

    trial_minutes = await settings.get_int("TRIAL_MINUTES", 60)
    trial_mb = await settings.get_int("TRIAL_MB", 600)

    try:
        username = f"trial_{user_id}"
        panel_username, sub_link = await panel.create_vpn_user(
            username=username,
            minutes=trial_minutes,
            mb=trial_mb,
            note=f"trial:{user_id}",
        )
    except Exception as exc:
        raise TrialError(f"مشکلی در ساخت اکانت تست پیش اومد.\nجزئیات فنی: {exc}")

    await db.mark_trial_used(user_id)
    return {
        "panel_username": panel_username,
        "sub_link": sub_link,
        "duration_label": _format_duration(trial_minutes),
        "size_label": _format_size(trial_mb),
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
        f"⏳ اعتبار: {result['duration_label']} | 📶 حجم: {result['size_label']}"
    )
