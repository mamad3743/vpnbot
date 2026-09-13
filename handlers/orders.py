from aiogram import F, Router
from aiogram.types import Message

import config
import database as db
import keyboards as kb

router = Router(name="orders")


@router.message(F.text == kb.BTN_ORDERS)
async def my_orders(message: Message):
    orders = await db.user_orders(message.from_user.id)
    if not orders:
        await message.answer("هنوز خریدی نداشتی.")
        return

    lines = ["📦 سرویس‌های خریداری‌شده:\n"]
    for o in orders:
        lines.append(
            f"• {o['plan_title']} — {o['price_paid']:,} {config.CURRENCY}\n"
            f"  یوزرنیم: <code>{o['panel_username']}</code>\n"
            f"  لینک: <code>{o['sub_link']}</code>\n"
        )
    await message.answer("\n".join(lines))


@router.message(F.text == kb.BTN_DISCOUNT)
async def discount_info(message: Message):
    await message.answer(
        "🎟 برای استفاده از کد تخفیف، ابتدا از «🛒 خرید سرویس» یک پلن رو انتخاب کن، "
        "بعد گزینه‌ی «وارد کردن کد تخفیف» رو بزن."
    )


@router.message(F.text == kb.BTN_SUPPORT)
async def support_info(message: Message):
    await message.answer("📞 برای ارتباط با پشتیبانی به آیدی زیر پیام بده:\n@your_support_id")
