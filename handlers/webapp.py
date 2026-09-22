import json

from aiogram import Router
from aiogram.types import Message
from aiogram.enums import ContentType

from handlers.plans import PurchaseError, perform_purchase
from handlers.trial import TrialError, create_trial

router = Router(name="webapp")


@router.message(lambda m: m.content_type == ContentType.WEB_APP_DATA)
async def on_web_app_data(message: Message):
    """Every action the Mini App triggers (buy a plan, request a trial, ...)
    arrives here as JSON via Telegram.WebApp.sendData()."""
    try:
        payload = json.loads(message.web_app_data.data)
    except Exception:
        await message.answer("❌ داده‌ی نامعتبر از فروشگاه دریافت شد.")
        return

    action = payload.get("action")

    if action == "buy":
        plan_id = payload.get("plan_id")
        discount_code = payload.get("discount_code")
        await message.answer("⏳ در حال ساخت سرویس شما روی سرور...")
        try:
            result = await perform_purchase(message.from_user.id, int(plan_id), discount_code)
        except PurchaseError as exc:
            await message.answer(f"❌ {exc}")
            return
        await message.answer(
            "✅ خرید از فروشگاه شیشه‌ای با موفقیت انجام شد!\n\n"
            f"👤 یوزرنیم: <code>{result['panel_username']}</code>\n"
            f"🔗 لینک اشتراک:\n<code>{result['sub_link']}</code>"
        )

    elif action == "trial":
        await message.answer("⏳ در حال ساخت اکانت تست...")
        try:
            result = await create_trial(message.from_user.id)
        except TrialError as exc:
            await message.answer(f"❌ {exc}")
            return
        await message.answer(
            "🎁 اکانت تست شما ساخته شد!\n\n"
            f"👤 یوزرنیم: <code>{result['panel_username']}</code>\n"
            f"🔗 لینک اشتراک:\n<code>{result['sub_link']}</code>"
        )

    else:
        await message.answer("❌ عملیات ناشناخته از فروشگاه دریافت شد.")
