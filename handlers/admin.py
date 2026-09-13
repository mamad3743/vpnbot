import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
from states import AdminFlow

router = Router(name="admin")


def admin_only(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@router.message(F.text == kb.BTN_ADMIN)
async def admin_menu(message: Message):
    if not admin_only(message.from_user.id):
        return
    await message.answer("⚙️ پنل مدیریت:", reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "adm:stats")
async def adm_stats(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    users_count = await db.count_users()
    orders_count = await db.count_orders()
    revenue = await db.total_revenue()
    await callback.message.answer(
        "📊 آمار ربات:\n\n"
        f"👥 کاربران: {users_count}\n"
        f"🛒 تعداد فروش: {orders_count}\n"
        f"💰 درآمد کل: {revenue:,} {config.CURRENCY}"
    )
    await callback.answer()


@router.callback_query(F.data == "adm:addplan")
async def adm_addplan(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    await state.set_state(AdminFlow.waiting_plan_info)
    await callback.message.answer(
        "پلن جدید رو با این فرمت بفرست:\n\n"
        "<code>عنوان|حجم به گیگابایت|روز|قیمت به تومان</code>\n\n"
        "مثال:\n<code>یک ماهه 50 گیگ|50|30|150000</code>\n\n"
        "برای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_plan_info)
async def save_plan(message: Message, state: FSMContext):
    try:
        title, gb, days, price = message.text.split("|")
        await db.add_plan(title.strip(), int(days), int(gb), int(price))
        await message.answer(f"✅ پلن «{title.strip()}» اضافه شد.")
    except Exception:
        await message.answer("❌ فرمت اشتباهه. دوباره تلاش کن یا /cancel بزن.")
        return
    await state.clear()


@router.callback_query(F.data == "adm:addcode")
async def adm_addcode(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    await state.set_state(AdminFlow.waiting_code_info)
    await callback.message.answer(
        "کد تخفیف جدید رو با این فرمت بفرست:\n\n"
        "<code>کد|درصد تخفیف|حداکثر تعداد استفاده|اعتبار به روز</code>\n"
        "(برای بدون محدودیت تعداد یا زمان، عدد 0 بذار)\n\n"
        "مثال:\n<code>OFF20|20|100|30</code>\n\n"
        "برای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_code_info)
async def save_code(message: Message, state: FSMContext):
    try:
        code, percent, max_uses, valid_days = message.text.split("|")
        expires_at = None
        if int(valid_days) > 0:
            expires_at = int(time.time()) + int(valid_days) * 86400
        await db.add_discount_code(code.strip(), int(percent), int(max_uses), expires_at)
        await message.answer(f"✅ کد تخفیف «{code.strip().upper()}» اضافه شد.")
    except Exception:
        await message.answer("❌ فرمت اشتباهه. دوباره تلاش کن یا /cancel بزن.")
        return
    await state.clear()


@router.callback_query(F.data == "adm:listcodes")
async def adm_listcodes(callback: CallbackQuery):
    if not admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    codes = await db.list_discount_codes()
    if not codes:
        await callback.message.answer("هیچ کد تخفیفی ثبت نشده.")
    else:
        lines = ["🎟 کدهای تخفیف:\n"]
        for c in codes:
            status = "✅ فعال" if c["is_active"] else "❌ غیرفعال"
            lines.append(
                f"• {c['code']} — {c['percent']}% — "
                f"استفاده: {c['used_count']}/{c['max_uses'] or '∞'} — {status}"
            )
        await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    if not admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    await state.set_state(AdminFlow.waiting_broadcast)
    await callback.message.answer("پیامی که می‌خوای برای همه کاربران ارسال بشه رو بفرست:")
    await callback.answer()


@router.message(AdminFlow.waiting_broadcast)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_ids = await db.all_user_ids()
    sent, failed = 0, 0
    status_msg = await message.answer(f"⏳ در حال ارسال به {len(user_ids)} کاربر...")
    for uid in user_ids:
        try:
            await message.copy_to(uid)
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ ارسال شد به {sent} نفر — ناموفق: {failed}")
