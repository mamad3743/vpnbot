import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
import panel
from states import BuyFlow

router = Router(name="plans")


def apply_discount(price: int, percent: int) -> int:
    return max(0, price - (price * percent) // 100)


@router.message(F.text == kb.BTN_BUY)
async def show_plans(message: Message):
    plans = await db.list_plans()
    if not plans:
        await message.answer("در حال حاضر پلنی برای فروش تعریف نشده. بعدا مراجعه کن 🙏")
        return
    await message.answer("یکی از پلن‌های زیر رو انتخاب کن 👇", reply_markup=kb.plans_kb(plans))


@router.callback_query(F.data.startswith("plan:"))
async def choose_plan(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    plan_row = await db.get_plan(plan_id)
    if not plan_row:
        await callback.answer("این پلن دیگه موجود نیست", show_alert=True)
        return

    await state.update_data(plan_id=plan_id, price=plan_row["price"], discount_code=None)
    balance = await db.get_wallet_balance(callback.from_user.id)
    text = (
        f"📦 پلن انتخابی: {plan_row['title']}\n"
        f"📶 حجم: {plan_row['gb']} گیگابایت\n"
        f"⏳ مدت: {plan_row['days']} روز\n"
        f"💰 قیمت: {plan_row['price']:,} {config.CURRENCY}\n\n"
        f"💳 موجودی کیف پول شما: {balance:,} {config.CURRENCY}"
    )
    await callback.message.edit_text(text, reply_markup=kb.confirm_purchase_kb(plan_id))
    await callback.answer()


@router.callback_query(F.data.startswith("enter_code:"))
async def ask_discount_code(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    await state.update_data(plan_id=plan_id)
    await state.set_state(BuyFlow.waiting_discount_code)
    await callback.message.answer("🎟 کد تخفیف رو ارسال کن (یا /cancel برای انصراف):")
    await callback.answer()


@router.message(BuyFlow.waiting_discount_code)
async def apply_code(message: Message, state: FSMContext):
    data = await state.get_data()
    plan_row = await db.get_plan(data["plan_id"])
    if not plan_row:
        await message.answer("پلن پیدا نشد، دوباره از منو شروع کن.")
        await state.clear()
        return

    code_row = await db.get_discount_code(message.text.strip())
    if not code_row:
        await message.answer("❌ کد تخفیف نامعتبر یا منقضی شده. دوباره تلاش کن یا /cancel بزن.")
        return
    if code_row["max_uses"] and code_row["used_count"] >= code_row["max_uses"]:
        await message.answer("❌ ظرفیت این کد تخفیف تموم شده.")
        return

    new_price = apply_discount(plan_row["price"], code_row["percent"])
    await state.update_data(price=new_price, discount_code=code_row["code"])
    await state.set_state(None)

    balance = await db.get_wallet_balance(message.from_user.id)
    text = (
        f"✅ کد تخفیف {code_row['percent']}% اعمال شد!\n\n"
        f"📦 پلن: {plan_row['title']}\n"
        f"💰 قیمت جدید: {new_price:,} {config.CURRENCY}\n"
        f"💳 موجودی کیف پول شما: {balance:,} {config.CURRENCY}"
    )
    await message.answer(text, reply_markup=kb.confirm_purchase_kb(plan_row["id"]))


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan_id = int(callback.data.split(":")[1])
    plan_row = await db.get_plan(plan_id)
    if not plan_row:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return

    price = data.get("price", plan_row["price"])
    discount_code = data.get("discount_code")

    ok = await db.deduct_wallet(callback.from_user.id, price)
    if not ok:
        await callback.answer("موجودی کیف پول کافی نیست ❌", show_alert=True)
        await callback.message.answer(
            "موجودی کیف پولت کافی نیست. اول شارژ کن 👇",
            reply_markup=kb.wallet_charge_kb(),
        )
        return

    await callback.message.edit_text("⏳ در حال ساخت سرویس شما روی سرور...")

    try:
        panel_username = f"u{callback.from_user.id}_{plan_id}_{int(time.time())}"
        panel_username, sub_link = await panel.create_vpn_user(
            username=panel_username,
            days=plan_row["days"],
            gb=plan_row["gb"],
            note=f"telegram:{callback.from_user.id}",
        )
    except Exception as exc:
        await db.add_to_wallet(callback.from_user.id, price)  # refund
        await callback.message.edit_text(
            "❌ مشکلی در ساخت سرویس پیش اومد و مبلغ به کیف پولت برگشت داده شد.\n"
            f"جزئیات فنی: {exc}"
        )
        return

    if discount_code:
        await db.use_discount_code(discount_code)

    await db.create_order(
        user_id=callback.from_user.id,
        plan_id=plan_id,
        plan_title=plan_row["title"],
        price_paid=price,
        discount_code=discount_code,
        panel_username=panel_username,
        sub_link=sub_link,
    )

    await state.clear()
    await callback.message.edit_text(
        "✅ خرید با موفقیت انجام شد!\n\n"
        f"👤 یوزرنیم: <code>{panel_username}</code>\n"
        f"🔗 لینک اشتراک:\n<code>{sub_link}</code>\n\n"
        "این لینک رو داخل اپلیکیشن کلاینت خودت (V2rayNG, Streisand, Hiddify, ...) وارد کن."
    )


@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("لغو شد")
