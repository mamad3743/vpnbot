from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram import F

import database as db
import keyboards as kb
import settings
from membership import get_missing_channels

router = Router(name="start")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Global /cancel: works no matter which FSM state the user is currently in.
    Registered in the first router so it always takes priority over step handlers."""
    if await state.get_state() is not None:
        await state.clear()
        await message.answer("عملیات لغو شد.")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)

    channels = await settings.get_list("FORCE_JOIN_CHANNELS")
    if channels:
        missing = await get_missing_channels(message.bot, message.from_user.id)
        if missing:
            await message.answer(
                "⛔️ برای استفاده از ربات، ابتدا باید در کانال(های) زیر عضو شوی:\n\n"
                "بعد از عضویت روی دکمه «بررسی کن» بزن.",
                reply_markup=await kb.join_channels_kb(),
            )
            return

    is_admin = await settings.is_admin(message.from_user.id)
    await message.answer(
        "👋 به ربات فروش VPN خوش اومدی!\n\n"
        "از منوی زیر یکی از گزینه‌ها رو انتخاب کن 👇",
        reply_markup=await kb.main_menu(is_admin=is_admin),
    )


@router.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery):
    missing = await get_missing_channels(callback.bot, callback.from_user.id)
    if missing:
        await callback.answer("هنوز عضو همه‌ی کانال‌ها نشدی ❌", show_alert=True)
        return

    await db.ensure_user(callback.from_user.id, callback.from_user.username)
    is_admin = await settings.is_admin(callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer(
        "✅ عضویت تایید شد! خوش اومدی 🎉",
        reply_markup=await kb.main_menu(is_admin=is_admin),
    )
    await callback.answer()
