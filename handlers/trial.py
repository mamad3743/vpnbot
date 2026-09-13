from aiogram import F, Router
from aiogram.types import Message

import config
import database as db
import keyboards as kb
import panel

router = Router(name="trial")


@router.message(F.text == kb.BTN_TRIAL)
async def get_trial(message: Message):
    if await db.has_used_trial(message.from_user.id):
        await message.answer("❌ شما قبلا از اکانت تست رایگان استفاده کردی.")
        return

    await message.answer("⏳ در حال ساخت اکانت تست...")
    try:
        username = f"trial_{message.from_user.id}"
        panel_username, sub_link = await panel.create_vpn_user(
            username=username,
            days=config.TRIAL_DAYS,
            gb=config.TRIAL_GB,
            note=f"trial:{message.from_user.id}",
        )
    except Exception as exc:
        await message.answer(f"❌ مشکلی در ساخت اکانت تست پیش اومد.\nجزئیات فنی: {exc}")
        return

    await db.mark_trial_used(message.from_user.id)
    await message.answer(
        "🎁 اکانت تست شما ساخته شد!\n\n"
        f"👤 یوزرنیم: <code>{panel_username}</code>\n"
        f"🔗 لینک اشتراک:\n<code>{sub_link}</code>\n\n"
        f"⏳ اعتبار: {config.TRIAL_DAYS} روز | 📶 حجم: {config.TRIAL_GB} گیگابایت"
    )
