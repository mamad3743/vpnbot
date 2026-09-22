from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import settings
from states import WalletFlow

router = Router(name="wallet")


@router.message(F.text == kb.BTN_WALLET)
async def wallet_menu(message: Message):
    currency = await settings.get("CURRENCY", "تومان")
    balance = await db.get_wallet_balance(message.from_user.id)
    text = (
        f"💳 موجودی کیف پول شما: {balance:,} {currency}\n\n"
        "برای شارژ، یکی از مبلغ‌های زیر رو انتخاب کن:"
    )
    await message.answer(text, reply_markup=kb.wallet_charge_kb())


@router.callback_query(F.data.startswith("charge:"))
async def choose_charge_amount(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split(":")[1])
    await state.update_data(amount=amount)
    await state.set_state(WalletFlow.waiting_receipt)

    currency = await settings.get("CURRENCY", "تومان")
    card_number = await settings.get("CARD_NUMBER", "تنظیم نشده")
    card_holder = await settings.get("CARD_HOLDER", "-")

    await callback.message.answer(
        f"💳 مبلغ {amount:,} {currency} رو به شماره کارت زیر واریز کن:\n\n"
        f"<code>{card_number}</code>\n"
        f"به نام: {card_holder}\n\n"
        "بعد از واریز، عکس رسید یا کد پیگیری تراکنش رو همینجا بفرست."
    )
    await callback.answer()


@router.message(WalletFlow.waiting_receipt)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount", 0)
    currency = await settings.get("CURRENCY", "تومان")

    request_id = await db.create_wallet_request(
        user_id=message.from_user.id,
        amount=amount,
        note=message.text or message.caption or "(بدون توضیح متنی - رسید به صورت عکس ارسال شد)",
    )
    await state.clear()

    await message.answer("✅ درخواست شارژ کیف پول شما برای ادمین ارسال شد. منتظر تایید بمون 🙏")

    admin_ids = await settings.get_admin_ids()
    for admin_id in admin_ids:
        try:
            caption = (
                f"🔔 درخواست شارژ کیف پول جدید #{request_id}\n"
                f"👤 کاربر: {message.from_user.id} (@{message.from_user.username or '-'})\n"
                f"💰 مبلغ: {amount:,} {currency}"
            )
            if message.photo:
                await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=caption,
                    reply_markup=kb.approve_wallet_kb(request_id),
                )
            else:
                caption += f"\n📝 پیام کاربر: {message.text}"
                await bot.send_message(
                    admin_id, caption, reply_markup=kb.approve_wallet_kb(request_id)
                )
        except Exception:
            pass


@router.callback_query(F.data.startswith("wallet_ok:"))
async def approve_wallet(callback: CallbackQuery, bot: Bot):
    if not await settings.is_admin(callback.from_user.id):
        await callback.answer("⛔️ فقط ادمین", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])
    req = await db.get_wallet_request(request_id)
    if not req or req["status"] != "pending":
        await callback.answer("این درخواست قبلا پردازش شده", show_alert=True)
        return

    currency = await settings.get("CURRENCY", "تومان")
    await db.add_to_wallet(req["user_id"], req["amount"])
    await db.set_wallet_request_status(request_id, "approved")

    try:
        if callback.message.caption:
            await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ تایید شد")
        else:
            await callback.message.edit_text(callback.message.text + "\n\n✅ تایید شد")
    except Exception:
        pass

    await bot.send_message(
        req["user_id"],
        f"✅ کیف پول شما به مبلغ {req['amount']:,} {currency} شارژ شد.",
    )
    await callback.answer("تایید شد")


@router.callback_query(F.data.startswith("wallet_no:"))
async def reject_wallet(callback: CallbackQuery, bot: Bot):
    if not await settings.is_admin(callback.from_user.id):
        await callback.answer("⛔️ فقط ادمین", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])
    req = await db.get_wallet_request(request_id)
    if not req or req["status"] != "pending":
        await callback.answer("این درخواست قبلا پردازش شده", show_alert=True)
        return

    await db.set_wallet_request_status(request_id, "rejected")
    try:
        if callback.message.caption:
            await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ رد شد")
        else:
            await callback.message.edit_text(callback.message.text + "\n\n❌ رد شد")
    except Exception:
        pass

    await bot.send_message(req["user_id"], "❌ متاسفانه درخواست شارژ کیف پول شما رد شد.")
    await callback.answer("رد شد")
