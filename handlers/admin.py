import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import settings
from states import AdminFlow

router = Router(name="admin")


async def admin_only(user_id: int) -> bool:
    return await settings.is_admin(user_id)


@router.message(F.text == kb.BTN_ADMIN)
async def admin_menu(message: Message):
    if not await admin_only(message.from_user.id):
        return
    await message.answer("⚙️ پنل مدیریت:", reply_markup=kb.admin_menu_kb())


# ---------------- stats ----------------

@router.callback_query(F.data == "adm:stats")
async def adm_stats(callback: CallbackQuery):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    currency = await settings.get("CURRENCY", "تومان")
    users_count = await db.count_users()
    orders_count = await db.count_orders()
    revenue = await db.total_revenue()
    await callback.message.answer(
        "📊 آمار ربات:\n\n"
        f"👥 کاربران: {users_count}\n"
        f"🛒 تعداد فروش: {orders_count}\n"
        f"💰 درآمد کل: {revenue:,} {currency}"
    )
    await callback.answer()


# ---------------- plans ----------------

@router.callback_query(F.data == "adm:addplan")
async def adm_addplan(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
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


# ---------------- discount codes ----------------

@router.callback_query(F.data == "adm:addcode")
async def adm_addcode(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
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
    if not await admin_only(callback.from_user.id):
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


# ---------------- broadcast ----------------

@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
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


# ---------------- panel settings ----------------

@router.callback_query(F.data == "adm:panel")
async def adm_panel(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    cur_url = await settings.get("PANEL_URL", "-")
    cur_user = await settings.get("PANEL_USERNAME", "-")
    await state.set_state(AdminFlow.waiting_panel_info)
    await callback.message.answer(
        f"مقادیر فعلی:\nآدرس: <code>{cur_url}</code>\nیوزرنیم: <code>{cur_user}</code>\n\n"
        "مقادیر جدید رو با این فرمت بفرست:\n\n"
        "<code>آدرس پنل|یوزرنیم ادمین|پسورد ادمین|شناسه گروه‌ها(اختیاری با کاما)</code>\n\n"
        "مثال:\n<code>https://panel.example.com|admin|MyPass123|</code>\n\n"
        "برای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_panel_info)
async def save_panel(message: Message, state: FSMContext):
    try:
        parts = message.text.split("|")
        url, username, password = parts[0].strip(), parts[1].strip(), parts[2].strip()
        group_ids = parts[3].strip() if len(parts) > 3 else ""
        await settings.set("PANEL_URL", url.rstrip("/"))
        await settings.set("PANEL_USERNAME", username)
        await settings.set("PANEL_PASSWORD", password)
        await settings.set("PANEL_GROUP_IDS", group_ids)
        await message.answer("✅ تنظیمات پنل ذخیره شد.")
    except Exception:
        await message.answer("❌ فرمت اشتباهه. دوباره تلاش کن یا /cancel بزن.")
        return
    await state.clear()


# ---------------- force join ----------------

@router.callback_query(F.data == "adm:forcejoin")
async def adm_forcejoin(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    current = await settings.get("FORCE_JOIN_CHANNELS", "")
    await state.set_state(AdminFlow.waiting_forcejoin_info)
    await callback.message.answer(
        f"کانال‌های فعلی: <code>{current or 'هیچی'}</code>\n\n"
        "یوزرنیم کانال‌ها رو با کاما جدا کن و بفرست (ربات باید ادمین این کانال‌ها باشه):\n"
        "<code>@channel1,@channel2</code>\n\n"
        "برای غیرفعال کردن عضویت اجباری، فقط عدد 0 بفرست.\n"
        "برای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_forcejoin_info)
async def save_forcejoin(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "0":
        await settings.set("FORCE_JOIN_CHANNELS", "")
        await message.answer("✅ عضویت اجباری غیرفعال شد.")
    else:
        channels = [c.strip() for c in text.split(",") if c.strip()]
        await settings.set_list("FORCE_JOIN_CHANNELS", channels)
        await message.answer(f"✅ {len(channels)} کانال ذخیره شد.")
    await state.clear()


# ---------------- payment settings ----------------

@router.callback_query(F.data == "adm:payment")
async def adm_payment(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    await state.set_state(AdminFlow.waiting_payment_info)
    await callback.message.answer(
        "اطلاعات پرداخت رو با این فرمت بفرست:\n\n"
        "<code>شماره کارت|نام صاحب کارت|واحد پول</code>\n\n"
        "مثال:\n<code>6037-XXXX-XXXX-XXXX|علی رضایی|تومان</code>\n\n"
        "برای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_payment_info)
async def save_payment(message: Message, state: FSMContext):
    try:
        card, holder, currency = message.text.split("|")
        await settings.set("CARD_NUMBER", card.strip())
        await settings.set("CARD_HOLDER", holder.strip())
        await settings.set("CURRENCY", currency.strip())
        await message.answer("✅ تنظیمات پرداخت ذخیره شد.")
    except Exception:
        await message.answer("❌ فرمت اشتباهه. دوباره تلاش کن یا /cancel بزن.")
        return
    await state.clear()


# ---------------- trial settings ----------------

@router.callback_query(F.data == "adm:trial")
async def adm_trial(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    days = await settings.get_int("TRIAL_DAYS", 1)
    gb = await settings.get_int("TRIAL_GB", 1)
    await state.set_state(AdminFlow.waiting_trial_info)
    await callback.message.answer(
        f"مقادیر فعلی: {days} روز / {gb} گیگ\n\n"
        "مقادیر جدید رو با این فرمت بفرست:\n\n"
        "<code>روز|گیگابایت</code>\n\nمثال:\n<code>1|2</code>\n\nبرای انصراف /cancel رو بزن."
    )
    await callback.answer()


@router.message(AdminFlow.waiting_trial_info)
async def save_trial(message: Message, state: FSMContext):
    try:
        days, gb = message.text.split("|")
        await settings.set("TRIAL_DAYS", str(int(days.strip())))
        await settings.set("TRIAL_GB", str(int(gb.strip())))
        await message.answer("✅ تنظیمات اکانت تست ذخیره شد.")
    except Exception:
        await message.answer("❌ فرمت اشتباهه. دوباره تلاش کن یا /cancel بزن.")
        return
    await state.clear()


# ---------------- mini app theme ----------------

@router.callback_query(F.data == "adm:theme")
async def adm_theme(callback: CallbackQuery):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    current = await settings.get("MINIAPP_ACCENT", "#2f80ed")
    await callback.message.answer(
        f"رنگ اصلی فعلی مینی‌اپ: <code>{current}</code>\n\nیکی از رنگ‌های زیر رو انتخاب کن:",
        reply_markup=kb.theme_color_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("theme_color:"))
async def set_theme_color(callback: CallbackQuery):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    color = callback.data.split(":")[1]
    await settings.set("MINIAPP_ACCENT", color)
    await callback.message.answer(f"✅ رنگ اصلی مینی‌اپ روی <code>{color}</code> تنظیم شد.")
    await callback.answer()


@router.callback_query(F.data == "theme_color_custom")
async def ask_custom_color(callback: CallbackQuery, state: FSMContext):
    if not await admin_only(callback.from_user.id):
        return await callback.answer("⛔️", show_alert=True)
    await state.set_state(AdminFlow.waiting_theme_custom_color)
    await callback.message.answer("کد هگز رنگ رو بفرست، مثلاً: <code>#ff5733</code>")
    await callback.answer()


@router.message(AdminFlow.waiting_theme_custom_color)
async def save_custom_color(message: Message, state: FSMContext):
    color = message.text.strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        await message.answer("❌ فرمت رنگ درست نیست. مثال درست: #ff5733")
        return
    await settings.set("MINIAPP_ACCENT", color)
    await message.answer(f"✅ رنگ اصلی مینی‌اپ روی <code>{color}</code> تنظیم شد.")
    await state.clear()
