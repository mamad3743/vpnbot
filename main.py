"""
Single-process web server for the bot.

Replaces the old long-polling bot.py. On boot it starts a tiny web server
with just an /install page. Once someone fills that form in (bot token +
first admin id), it:
  - validates the token against Telegram
  - saves everything to the `settings` table (so it survives restarts as
    long as a persistent volume is mounted at DB_PATH's directory)
  - creates the aiogram Bot/Dispatcher in memory
  - registers a Telegram webhook pointing at this same server

From then on this same process also serves the Telegram Mini App (static
HTML) and a small JSON API it uses (plans list, live theme color, wallet
balance).
"""

import asyncio
import logging
import secrets

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Update
from aiohttp import web

import database as db
import miniapp_api
import settings
from middlewares import ForceJoinMiddleware
from handlers import admin, orders, plans, start, trial, wallet, webapp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

runtime: dict = {"bot": None, "dp": None}


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # start.router first: its global /cancel handler must win over
    # state-specific handlers registered by later routers.
    dp.include_router(start.router)
    dp.include_router(webapp.router)
    dp.include_router(plans.router)
    dp.include_router(trial.router)
    dp.include_router(wallet.router)
    dp.include_router(orders.router)
    dp.include_router(admin.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        """Catches any exception raised inside a handler so a broken button
        shows an error instead of silently doing nothing (dead spinner)."""
        log.exception("Unhandled error while processing update", exc_info=event.exception)
        update = event.update
        try:
            if update.callback_query:
                await update.callback_query.answer("❌ خطای داخلی. دوباره امتحان کن.", show_alert=True)
            elif update.message:
                await update.message.answer("❌ یه خطای داخلی پیش اومد. دوباره امتحان کن یا /cancel بزن.")
        except Exception:
            pass
        return True

    return dp


async def bootstrap_bot(base_url: str) -> None:
    token = await settings.get("BOT_TOKEN", "")
    if not token:
        return

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    webhook_secret = await settings.get("WEBHOOK_SECRET", "")
    if not webhook_secret:
        webhook_secret = secrets.token_urlsafe(24)
        await settings.set("WEBHOOK_SECRET", webhook_secret)

    webhook_url = f"{base_url.rstrip('/')}/webhook"
    await bot.set_webhook(webhook_url, secret_token=webhook_secret, drop_pending_updates=True)

    runtime["bot"] = bot
    runtime["dp"] = dp
    log.info("Bot bootstrapped, webhook set to %s", webhook_url)


# ---------------- routes ----------------

INSTALL_FORM = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>نصب بات فروش VPN</title>
<style>
body{{font-family:-apple-system,Tahoma,sans-serif;background:#0f1115;color:#e7e9ee;max-width:480px;margin:40px auto;padding:0 18px;line-height:1.8}}
h1{{font-size:1.3rem}}
label{{display:block;margin-top:16px;font-size:.9rem;color:#c6cad3}}
input{{width:100%;box-sizing:border-box;padding:11px 12px;margin-top:6px;border-radius:8px;border:1px solid #2b2f3a;background:#171a21;color:#fff;font-size:.95rem}}
button{{margin-top:22px;width:100%;padding:14px;border:0;border-radius:10px;background:#2f80ed;color:#fff;font-size:1rem;font-weight:bold}}
small{{color:#8a90a0}}
.box{{background:#171a21;border:1px solid #2b2f3a;border-radius:10px;padding:14px;margin-top:14px;font-size:.88rem}}
</style></head><body>
<h1>🚀 نصب بات فروش VPN</h1>
<div class="box">
دامنه‌ی تشخیص داده‌شده: <code>{base_url}</code><br>
بقیه‌ی تنظیمات (پنل PasarGuard، عضویت اجباری، کارت بانکی، رنگ مینی‌اپ و...) رو بعد از نصب،
از داخل خود بات و از منوی «⚙️ پنل مدیریت» تنظیم می‌کنی.
</div>
<form method="POST" action="/install">
  <label>توکن بات (از BotFather)
    <input name="bot_token" required>
  </label>
  <label>آیدی عددی ادمین اول (از @userinfobot بگیر)
    <input name="admin_id" required>
  </label>
  <label>دامنه (اختیاری — اگه خالی بمونه خودکار تشخیص داده میشه)
    <input name="base_url" placeholder="{base_url}">
  </label>
  <button type="submit">🚀 نصب و راه‌اندازی</button>
</form>
</body></html>"""

INSTALL_SUCCESS = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>نصب موفق</title>
<style>body{{font-family:-apple-system,Tahoma,sans-serif;background:#0f1115;color:#e7e9ee;max-width:480px;margin:40px auto;padding:0 18px;line-height:1.9}}
.box{{background:#122019;border:1px solid #2f8f4e;border-radius:10px;padding:16px}}</style></head><body>
<div class="box">
✅ نصب با موفقیت انجام شد و بات روشنه!<br><br>
حالا برو تو تلگرام سراغ باتت و /start رو بزن، منوی «⚙️ پنل مدیریت» همونجا در دسترسته.
</div>
</body></html>"""

ALREADY_INSTALLED = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><body style="font-family:sans-serif;background:#0f1115;color:#e7e9ee;text-align:center;padding-top:80px">
✅ این بات قبلا نصب و راه‌اندازی شده.
</body></html>"""


async def handle_index(request: web.Request) -> web.Response:
    if await settings.is_installed():
        return web.Response(text="✅ Bot is running.", content_type="text/plain")
    raise web.HTTPFound("/install")


async def handle_install_get(request: web.Request) -> web.Response:
    if await settings.is_installed():
        return web.Response(text=ALREADY_INSTALLED, content_type="text/html")
    base_url = f"https://{request.host}"
    return web.Response(text=INSTALL_FORM.format(base_url=base_url), content_type="text/html")


async def handle_install_post(request: web.Request) -> web.Response:
    if await settings.is_installed():
        return web.Response(text=ALREADY_INSTALLED, content_type="text/html", status=400)

    data = await request.post()
    bot_token = str(data.get("bot_token", "")).strip()
    admin_id = str(data.get("admin_id", "")).strip()
    base_url_override = str(data.get("base_url", "")).strip()

    if not bot_token or not admin_id.isdigit():
        return web.Response(text="اطلاعات ناقص یا نامعتبره. برگرد و دوباره امتحان کن.", status=400)

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.telegram.org/bot{bot_token}/getMe") as resp:
            payload = await resp.json()
    if not payload.get("ok"):
        return web.Response(text="❌ توکن بات نامعتبره. برگرد و دوباره امتحان کن.", status=400)

    base_url = (base_url_override or f"https://{request.host}").rstrip("/")

    await settings.set("BOT_TOKEN", bot_token)
    await settings.set_list("ADMIN_IDS", [admin_id])
    await settings.set("BASE_URL", base_url)
    await settings.set_bool("INSTALLED", True)

    await bootstrap_bot(base_url)

    return web.Response(text=INSTALL_SUCCESS, content_type="text/html")


async def handle_webhook(request: web.Request) -> web.Response:
    bot = runtime.get("bot")
    dp = runtime.get("dp")
    if not bot or not dp:
        return web.Response(status=404, text="bot not installed yet")

    webhook_secret = await settings.get("WEBHOOK_SECRET", "")
    if webhook_secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header != webhook_secret:
            return web.Response(status=403)

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return web.Response()


async def on_startup(app: web.Application) -> None:
    await db.init_db()
    if await settings.is_installed():
        base_url = await settings.get("BASE_URL", "")
        if base_url:
            await bootstrap_bot(base_url)


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)

    app.router.add_get("/", handle_index)
    app.router.add_get("/install", handle_install_get)
    app.router.add_post("/install", handle_install_post)
    app.router.add_post("/webhook", handle_webhook)

    miniapp_api.register_routes(app)

    return app


if __name__ == "__main__":
    import config

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=config.PORT)
