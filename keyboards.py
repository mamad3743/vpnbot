from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import settings

BTN_BUY = "🛒 خرید سرویس"
BTN_SHOP = "🛍 فروشگاه شیشه‌ای"
BTN_TRIAL = "🎁 اکانت تست رایگان"
BTN_WALLET = "💳 کیف پول من"
BTN_DISCOUNT = "🎟 کد تخفیف"
BTN_ORDERS = "📦 سرویس‌های من"
BTN_SUPPORT = "📞 پشتیبانی"
BTN_ADMIN = "⚙️ پنل مدیریت"


async def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    base_url = await settings.get("BASE_URL", "")

    if base_url:
        b.row(KeyboardButton(text=BTN_SHOP, web_app=WebAppInfo(url=f"{base_url}/miniapp/")))

    b.row(KeyboardButton(text=BTN_BUY, style="primary"))
    b.row(
        KeyboardButton(text=BTN_TRIAL, style="success"),
        KeyboardButton(text=BTN_WALLET),
    )
    b.row(
        KeyboardButton(text=BTN_DISCOUNT),
        KeyboardButton(text=BTN_ORDERS),
    )
    b.row(KeyboardButton(text=BTN_SUPPORT))
    if is_admin:
        b.row(KeyboardButton(text=BTN_ADMIN, style="danger"))
    return b.as_markup(resize_keyboard=True)


async def join_channels_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    channels = await settings.get_list("FORCE_JOIN_CHANNELS")
    for ch in channels:
        handle = ch.lstrip("@")
        b.row(InlineKeyboardButton(text=f"عضویت در {ch}", url=f"https://t.me/{handle}"))
    b.row(InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_join"))
    return b.as_markup()


async def plans_kb(plans) -> InlineKeyboardMarkup:
    currency = await settings.get("CURRENCY", "تومان")
    b = InlineKeyboardBuilder()
    for p in plans:
        label = f"{p['title']} | {p['gb']}GB | {p['days']} روز | {p['price']:,} {currency}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"plan:{p['id']}"))
    return b.as_markup()


def confirm_purchase_kb(plan_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ تایید و پرداخت از کیف پول", callback_data=f"confirm_buy:{plan_id}"))
    b.row(InlineKeyboardButton(text="🎟 وارد کردن کد تخفیف", callback_data=f"enter_code:{plan_id}"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    return b.as_markup()


def wallet_charge_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for amount in (50000, 100000, 200000, 500000):
        b.button(text=f"{amount:,}", callback_data=f"charge:{amount}")
    b.adjust(2)
    return b.as_markup()


def approve_wallet_kb(request_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"wallet_ok:{request_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"wallet_no:{request_id}"),
    )
    return b.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 آمار فروش", callback_data="adm:stats"))
    b.row(InlineKeyboardButton(text="➕ افزودن پلن", callback_data="adm:addplan"))
    b.row(InlineKeyboardButton(text="🎟 افزودن کد تخفیف", callback_data="adm:addcode"))
    b.row(InlineKeyboardButton(text="📋 لیست کدهای تخفیف", callback_data="adm:listcodes"))
    b.row(InlineKeyboardButton(text="📢 ارسال پیام همگانی", callback_data="adm:broadcast"))
    b.row(InlineKeyboardButton(text="🔌 تنظیمات پنل PasarGuard", callback_data="adm:panel"))
    b.row(InlineKeyboardButton(text="🔒 عضویت اجباری", callback_data="adm:forcejoin"))
    b.row(InlineKeyboardButton(text="💳 تنظیمات پرداخت", callback_data="adm:payment"))
    b.row(InlineKeyboardButton(text="🎁 تنظیمات اکانت تست", callback_data="adm:trial"))
    b.row(InlineKeyboardButton(text="🎨 تم و رنگ مینی‌اپ", callback_data="adm:theme"))
    return b.as_markup()


def theme_color_kb() -> InlineKeyboardMarkup:
    colors = [
        ("🔵 آبی", "#2f80ed"),
        ("🟣 بنفش", "#8e44ec"),
        ("🟢 سبز", "#1fb35a"),
        ("🔴 قرمز", "#e5484d"),
        ("🟠 نارنجی", "#f2994a"),
        ("⚫️ مشکی", "#1a1a1a"),
    ]
    b = InlineKeyboardBuilder()
    for label, hex_code in colors:
        b.button(text=label, callback_data=f"theme_color:{hex_code}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="🎯 رنگ دلخواه (کد هگز بفرست)", callback_data="theme_color_custom"))
    return b.as_markup()
