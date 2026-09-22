"""
Token-protected web admin panel.

Login: the admin gets a token from inside the bot ("⚙️ پنل مدیریت" ->
"🌐 پنل وب و توکن API", or /webtoken to rotate it). That token is entered
once at /admin/login; on success a random session id is issued and stored
in memory (this is a single-process app, same pattern as the FSM storage),
kept in an HttpOnly cookie for 12 hours.

Nothing here talks to the PasarGuard panel directly except through the same
`panel.create_vpn_user` used by the bot, so behaviour stays identical
between the Telegram admin menu and this web panel — this is just another
front door onto the same `settings` / `database` layer.
"""

import hmac
import secrets
import time
from typing import Optional

from aiohttp import web

import database as db
import handlers.trial as trial_mod
import settings

SESSION_TTL = 12 * 3600
SESSION_COOKIE = "admin_session"

# session_id -> expiry (epoch seconds). In-memory on purpose: same lifetime
# guarantees as the bot's FSM storage, and simplest thing that works for a
# single admin/small team on a single process.
_sessions: dict[str, float] = {}


def invalidate_all_sessions() -> None:
    _sessions.clear()


def _new_session() -> str:
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = time.time() + SESSION_TTL
    return sid


def _is_valid_session(sid: Optional[str]) -> bool:
    if not sid or sid not in _sessions:
        return False
    if _sessions[sid] < time.time():
        del _sessions[sid]
        return False
    return True


async def _require_admin(request: web.Request) -> Optional[web.Response]:
    """Returns a redirect response if the request is NOT authenticated,
    otherwise None (caller should proceed)."""
    sid = request.cookies.get(SESSION_COOKIE)
    if not _is_valid_session(sid):
        raise web.HTTPFound("/admin/login")
    return None


# ---------------- layout ----------------

NAV = [
    ("/admin/dashboard", "📊 آمار"),
    ("/admin/plans", "📦 پلن‌ها"),
    ("/admin/codes", "🎟 کدهای تخفیف"),
    ("/admin/wallet", "💳 درخواست‌های شارژ"),
    ("/admin/orders", "🧾 سفارش‌ها"),
    ("/admin/settings", "⚙️ تنظیمات"),
]


def _page(title: str, body: str, active: str = "") -> web.Response:
    nav_html = "".join(
        f'<a class="nav-link{" active" if href == active else ""}" href="{href}">{label}</a>'
        for href, label in NAV
    )
    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — پنل مدیریت</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{font-family:-apple-system,Tahoma,sans-serif;background:#0f1115;color:#e7e9ee;margin:0;line-height:1.8}}
header{{background:#171a21;border-bottom:1px solid #2b2f3a;padding:14px 20px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;position:sticky;top:0}}
header b{{margin-left:auto;color:#8a90a0;font-weight:normal;font-size:.85rem}}
.nav-link{{color:#c6cad3;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:.9rem}}
.nav-link:hover{{background:#20242e}}
.nav-link.active{{background:#2f80ed;color:#fff}}
main{{max-width:880px;margin:26px auto;padding:0 18px}}
h1{{font-size:1.25rem;margin-top:0}}
.card{{background:#171a21;border:1px solid #2b2f3a;border-radius:12px;padding:18px;margin-bottom:16px}}
.stat{{display:inline-block;min-width:150px;margin:6px 14px 6px 0}}
.stat b{{display:block;font-size:1.5rem}}
.stat span{{color:#8a90a0;font-size:.85rem}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
th,td{{text-align:right;padding:8px 6px;border-bottom:1px solid #2b2f3a}}
th{{color:#8a90a0;font-weight:normal}}
label{{display:block;margin-top:14px;font-size:.88rem;color:#c6cad3}}
input,select{{width:100%;box-sizing:border-box;padding:10px 12px;margin-top:5px;border-radius:8px;border:1px solid #2b2f3a;background:#0f1115;color:#fff;font-size:.92rem}}
button{{margin-top:16px;padding:10px 18px;border:0;border-radius:8px;background:#2f80ed;color:#fff;font-size:.92rem;font-weight:bold;cursor:pointer}}
button.danger{{background:#e5484d}}
button.ghost{{background:#20242e;color:#c6cad3}}
button.small{{margin-top:0;padding:6px 12px;font-size:.82rem}}
.pill{{display:inline-block;padding:2px 9px;border-radius:99px;font-size:.78rem}}
.pill.ok{{background:#122019;color:#4ade80;border:1px solid #2f8f4e}}
.pill.off{{background:#211417;color:#f87171;border:1px solid #7f2b2b}}
.muted{{color:#8a90a0;font-size:.85rem}}
.row-actions{{display:flex;gap:8px}}
code{{background:#0f1115;padding:2px 6px;border-radius:5px}}
hr{{border:none;border-top:1px solid #2b2f3a;margin:18px 0}}
</style></head><body>
<header>{nav_html}<b>⚙️ پنل مدیریت وب</b></header>
<main>{body}</main>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


# ---------------- login/logout ----------------

LOGIN_FORM = """
<div class="card" style="max-width:360px;margin:60px auto 0">
<h1>🔐 ورود به پنل مدیریت</h1>
{error}
<form method="POST" action="/admin/login">
  <label>توکن API
    <input name="token" type="password" required autofocus>
  </label>
  <button type="submit">ورود</button>
</form>
<p class="muted">توکن رو از داخل بات، منوی «⚙️ پنل مدیریت → 🌐 پنل وب و توکن API» بگیر.</p>
</div>
"""


async def handle_login_get(request: web.Request) -> web.Response:
    sid = request.cookies.get(SESSION_COOKIE)
    if _is_valid_session(sid):
        raise web.HTTPFound("/admin/dashboard")
    return _page("ورود", LOGIN_FORM.format(error=""))


async def handle_login_post(request: web.Request) -> web.Response:
    data = await request.post()
    token = str(data.get("token", "")).strip()
    real_token = await settings.get("ADMIN_API_TOKEN", "")

    if not real_token or not token or not hmac.compare_digest(token, real_token):
        return _page(
            "ورود",
            LOGIN_FORM.format(
                error='<p style="color:#f87171">❌ توکن نادرسته.</p>'
            ),
        )

    sid = _new_session()
    resp = web.HTTPFound("/admin/dashboard")
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="Strict",
        secure=request.scheme == "https",
    )
    return resp


async def handle_logout(request: web.Request) -> web.Response:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        _sessions.pop(sid, None)
    resp = web.HTTPFound("/admin/login")
    resp.del_cookie(SESSION_COOKIE)
    return resp


async def handle_admin_root(request: web.Request) -> web.Response:
    raise web.HTTPFound("/admin/dashboard")


# ---------------- dashboard ----------------

async def handle_dashboard(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    currency = await settings.get("CURRENCY", "تومان")
    users_count = await db.count_users()
    orders_count = await db.count_orders()
    revenue = await db.total_revenue()
    pending = await db.list_wallet_requests("pending")
    trial_hours, trial_mb = await trial_mod.get_trial_limits()

    body = f"""
<h1>📊 آمار ربات</h1>
<div class="card">
  <div class="stat"><b>{users_count:,}</b><span>👥 کاربران</span></div>
  <div class="stat"><b>{orders_count:,}</b><span>🛒 تعداد فروش</span></div>
  <div class="stat"><b>{revenue:,}</b><span>💰 درآمد کل ({currency})</span></div>
  <div class="stat"><b>{len(pending)}</b><span>⏳ درخواست شارژ در انتظار</span></div>
  <div class="stat"><b>{trial_hours} ساعت / {trial_mb} مگ</b><span>🎁 اکانت تست فعلی</span></div>
</div>
"""
    return _page("داشبورد", body, active="/admin/dashboard")


# ---------------- plans ----------------

async def handle_plans(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    currency = await settings.get("CURRENCY", "تومان")
    plans = await db.list_plans(active_only=False)

    rows = ""
    for p in plans:
        status = '<span class="pill ok">فعال</span>' if p["is_active"] else '<span class="pill off">غیرفعال</span>'
        toggle_label = "غیرفعال کردن" if p["is_active"] else "فعال کردن"
        rows += f"""<tr>
  <td>{p['title']}</td><td>{p['gb']} گیگ</td><td>{p['days']} روز</td>
  <td>{p['price']:,} {currency}</td><td>{status}</td>
  <td><form method="POST" action="/admin/plans/{p['id']}/toggle">
    <button class="small ghost" type="submit">{toggle_label}</button></form></td>
</tr>"""

    body = f"""
<h1>📦 پلن‌ها</h1>
<div class="card">
<table><tr><th>عنوان</th><th>حجم</th><th>مدت</th><th>قیمت</th><th>وضعیت</th><th></th></tr>
{rows or '<tr><td colspan="6" class="muted">پلنی ثبت نشده.</td></tr>'}
</table>
</div>
<div class="card">
<h1 style="font-size:1.05rem">➕ افزودن پلن جدید</h1>
<form method="POST" action="/admin/plans/add">
  <label>عنوان<input name="title" required></label>
  <label>حجم (گیگابایت)<input name="gb" type="number" min="1" required></label>
  <label>مدت (روز)<input name="days" type="number" min="1" required></label>
  <label>قیمت ({currency})<input name="price" type="number" min="0" required></label>
  <button type="submit">افزودن پلن</button>
</form>
</div>
"""
    return _page("پلن‌ها", body, active="/admin/plans")


async def handle_plans_add(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    try:
        title = str(data["title"]).strip()
        gb = int(data["gb"])
        days = int(data["days"])
        price = int(data["price"])
        if not title or gb <= 0 or days <= 0 or price < 0:
            raise ValueError
        plan_id = await db.add_plan(title, days, gb, price)
        await db.set_plan_color(plan_id, "")
    except Exception:
        pass
    raise web.HTTPFound("/admin/plans")


async def handle_plan_toggle(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    plan_id = int(request.match_info["plan_id"])
    plan_row = await db.get_plan(plan_id)
    if plan_row:
        await db.set_plan_active(plan_id, not plan_row["is_active"])
    raise web.HTTPFound("/admin/plans")


# ---------------- discount codes ----------------

async def handle_codes(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    codes = await db.list_discount_codes()

    rows = ""
    for c in codes:
        status = '<span class="pill ok">فعال</span>' if c["is_active"] else '<span class="pill off">غیرفعال</span>'
        toggle_label = "غیرفعال کردن" if c["is_active"] else "فعال کردن"
        rows += f"""<tr>
  <td>{c['code']}</td><td>{c['percent']}%</td>
  <td>{c['used_count']}/{c['max_uses'] or '∞'}</td><td>{status}</td>
  <td><form method="POST" action="/admin/codes/{c['id']}/toggle">
    <button class="small ghost" type="submit">{toggle_label}</button></form></td>
</tr>"""

    body = f"""
<h1>🎟 کدهای تخفیف</h1>
<div class="card">
<table><tr><th>کد</th><th>درصد</th><th>استفاده</th><th>وضعیت</th><th></th></tr>
{rows or '<tr><td colspan="5" class="muted">کدی ثبت نشده.</td></tr>'}
</table>
</div>
<div class="card">
<h1 style="font-size:1.05rem">➕ افزودن کد تخفیف</h1>
<form method="POST" action="/admin/codes/add">
  <label>کد<input name="code" required></label>
  <label>درصد تخفیف<input name="percent" type="number" min="1" max="100" required></label>
  <label>حداکثر تعداد استفاده (۰ = نامحدود)<input name="max_uses" type="number" min="0" value="0"></label>
  <label>اعتبار به روز (۰ = بدون انقضا)<input name="valid_days" type="number" min="0" value="0"></label>
  <button type="submit">افزودن کد</button>
</form>
</div>
"""
    return _page("کدهای تخفیف", body, active="/admin/codes")


async def handle_codes_add(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    try:
        code = str(data["code"]).strip()
        percent = int(data["percent"])
        max_uses = int(data.get("max_uses", 0) or 0)
        valid_days = int(data.get("valid_days", 0) or 0)
        if not code or not (1 <= percent <= 100):
            raise ValueError
        expires_at = int(time.time()) + valid_days * 86400 if valid_days > 0 else None
        await db.add_discount_code(code, percent, max_uses, expires_at)
    except Exception:
        pass
    raise web.HTTPFound("/admin/codes")


async def handle_code_toggle(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    code_id = int(request.match_info["code_id"])
    codes = await db.list_discount_codes()
    row = next((c for c in codes if c["id"] == code_id), None)
    if row:
        await db.set_discount_code_active(code_id, not row["is_active"])
    raise web.HTTPFound("/admin/codes")


# ---------------- wallet requests ----------------

async def handle_wallet(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    currency = await settings.get("CURRENCY", "تومان")
    pending = await db.list_wallet_requests("pending")

    rows = ""
    for w in pending:
        rows += f"""<tr>
  <td>#{w['id']}</td><td>{w['user_id']}</td><td>{w['amount']:,} {currency}</td>
  <td class="muted">{(w['note'] or '')[:60]}</td>
  <td class="row-actions">
    <form method="POST" action="/admin/wallet/{w['id']}/approve"><button class="small" type="submit">✅ تایید</button></form>
    <form method="POST" action="/admin/wallet/{w['id']}/reject"><button class="small danger" type="submit">❌ رد</button></form>
  </td>
</tr>"""

    body = f"""
<h1>💳 درخواست‌های شارژ کیف پول (در انتظار)</h1>
<div class="card">
<table><tr><th>#</th><th>کاربر</th><th>مبلغ</th><th>توضیح</th><th></th></tr>
{rows or '<tr><td colspan="5" class="muted">درخواست در انتظاری نیست.</td></tr>'}
</table>
</div>
"""
    return _page("درخواست‌های شارژ", body, active="/admin/wallet")


async def _finish_wallet_request(request: web.Request, approve: bool) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    request_id = int(request.match_info["request_id"])
    req = await db.get_wallet_request(request_id)
    if req and req["status"] == "pending":
        currency = await settings.get("CURRENCY", "تومان")
        if approve:
            await db.add_to_wallet(req["user_id"], req["amount"])
            await db.set_wallet_request_status(request_id, "approved")
            notify = f"✅ کیف پول شما به مبلغ {req['amount']:,} {currency} شارژ شد."
        else:
            await db.set_wallet_request_status(request_id, "rejected")
            notify = "❌ متاسفانه درخواست شارژ کیف پول شما رد شد."
        bot = runtime_ref.get("bot") if runtime_ref else None
        if bot:
            try:
                await bot.send_message(req["user_id"], notify)
            except Exception:
                pass
    raise web.HTTPFound("/admin/wallet")


async def handle_wallet_approve(request: web.Request) -> web.Response:
    return await _finish_wallet_request(request, approve=True)


async def handle_wallet_reject(request: web.Request) -> web.Response:
    return await _finish_wallet_request(request, approve=False)


# ---------------- orders ----------------

async def handle_orders(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    currency = await settings.get("CURRENCY", "تومان")
    orders = await db.recent_orders(100)

    rows = "".join(
        f"""<tr>
  <td>#{o['id']}</td><td>{o['user_id']}</td><td>{o['plan_title'] or '-'}</td>
  <td>{o['price_paid']:,} {currency}</td><td class="muted">{o['panel_username'] or '-'}</td>
</tr>"""
        for o in orders
    )
    body = f"""
<h1>🧾 آخرین سفارش‌ها</h1>
<div class="card">
<table><tr><th>#</th><th>کاربر</th><th>پلن</th><th>مبلغ</th><th>یوزرنیم پنل</th></tr>
{rows or '<tr><td colspan="5" class="muted">سفارشی ثبت نشده.</td></tr>'}
</table>
</div>
"""
    return _page("سفارش‌ها", body, active="/admin/orders")


# ---------------- settings ----------------

async def handle_settings(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    panel_url = await settings.get("PANEL_URL", "")
    panel_user = await settings.get("PANEL_USERNAME", "")
    panel_groups = await settings.get("PANEL_GROUP_IDS", "")
    card_number = await settings.get("CARD_NUMBER", "")
    card_holder = await settings.get("CARD_HOLDER", "")
    currency = await settings.get("CURRENCY", "تومان")
    channels = await settings.get("FORCE_JOIN_CHANNELS", "")
    support = await settings.get("SUPPORT_USERNAME", "")
    trial_hours, trial_mb = await trial_mod.get_trial_limits()
    shop_name = await settings.get("SHOP_NAME", "فروشگاه VPN")

    body = f"""
<h1>⚙️ تنظیمات</h1>

<div class="card">
<h1 style="font-size:1.05rem">🔌 پنل PasarGuard</h1>
<form method="POST" action="/admin/settings/panel">
  <label>آدرس پنل<input name="url" value="{panel_url}" placeholder="https://panel.example.com"></label>
  <label>یوزرنیم ادمین<input name="username" value="{panel_user}"></label>
  <label>پسورد ادمین (خالی = بدون تغییر)<input name="password" type="password" placeholder="••••••••"></label>
  <label>شناسه گروه‌ها (اختیاری، با کاما)<input name="group_ids" value="{panel_groups}"></label>
  <button type="submit">ذخیره</button>
</form>
</div>

<div class="card">
<h1 style="font-size:1.05rem">💳 تنظیمات پرداخت</h1>
<form method="POST" action="/admin/settings/payment">
  <label>شماره کارت<input name="card_number" value="{card_number}"></label>
  <label>نام صاحب کارت<input name="card_holder" value="{card_holder}"></label>
  <label>واحد پول<input name="currency" value="{currency}"></label>
  <button type="submit">ذخیره</button>
</form>
</div>

<div class="card">
<h1 style="font-size:1.05rem">🔒 عضویت اجباری</h1>
<form method="POST" action="/admin/settings/forcejoin">
  <label>یوزرنیم کانال‌ها (با کاما، خالی = غیرفعال)<input name="channels" value="{channels}" placeholder="@channel1,@channel2"></label>
  <button type="submit">ذخیره</button>
</form>
</div>

<div class="card">
<h1 style="font-size:1.05rem">🎁 اکانت تست رایگان</h1>
<form method="POST" action="/admin/settings/trial">
  <label>اعتبار (ساعت)<input name="hours" type="number" min="1" value="{trial_hours}"></label>
  <label>حجم (مگابایت)<input name="mb" type="number" min="1" value="{trial_mb}"></label>
  <button type="submit">ذخیره</button>
</form>
</div>

<div class="card">
<h1 style="font-size:1.05rem">🏪 فروشگاه و پشتیبانی</h1>
<form method="POST" action="/admin/settings/shop">
  <label>نام فروشگاه<input name="shop_name" value="{shop_name}"></label>
  <label>آیدی پشتیبانی<input name="support_username" value="{support}" placeholder="@your_support_id"></label>
  <button type="submit">ذخیره</button>
</form>
</div>
"""
    return _page("تنظیمات", body, active="/admin/settings")


async def handle_settings_panel(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    await settings.set("PANEL_URL", str(data.get("url", "")).strip().rstrip("/"))
    await settings.set("PANEL_USERNAME", str(data.get("username", "")).strip())
    password = str(data.get("password", "")).strip()
    if password:
        await settings.set("PANEL_PASSWORD", password)
    await settings.set("PANEL_GROUP_IDS", str(data.get("group_ids", "")).strip())
    raise web.HTTPFound("/admin/settings")


async def handle_settings_payment(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    await settings.set("CARD_NUMBER", str(data.get("card_number", "")).strip())
    await settings.set("CARD_HOLDER", str(data.get("card_holder", "")).strip())
    await settings.set("CURRENCY", str(data.get("currency", "تومان")).strip() or "تومان")
    raise web.HTTPFound("/admin/settings")


async def handle_settings_forcejoin(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    raw = str(data.get("channels", "")).strip()
    channels = [c.strip() for c in raw.split(",") if c.strip()]
    await settings.set_list("FORCE_JOIN_CHANNELS", channels)
    raise web.HTTPFound("/admin/settings")


async def handle_settings_trial(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    try:
        hours = int(data["hours"])
        mb = int(data["mb"])
        if hours > 0 and mb > 0:
            await settings.set("TRIAL_HOURS", str(hours))
            await settings.set("TRIAL_MB", str(mb))
    except Exception:
        pass
    raise web.HTTPFound("/admin/settings")


async def handle_settings_shop(request: web.Request) -> web.Response:
    if (r := await _require_admin(request)) is not None:
        return r
    data = await request.post()
    await settings.set("SHOP_NAME", str(data.get("shop_name", "")).strip() or "فروشگاه VPN")
    await settings.set("SUPPORT_USERNAME", str(data.get("support_username", "")).strip())
    raise web.HTTPFound("/admin/settings")


# ---------------- wiring ----------------

runtime_ref: Optional[dict] = None


def register_routes(app: web.Application, runtime: dict) -> None:
    """`runtime` is main.py's shared {"bot": ..., "dp": ...} dict — kept as a
    reference (not a copy) so wallet-approval notifications can reach the
    live bot instance without a circular import on main.py."""
    global runtime_ref
    runtime_ref = runtime

    app.router.add_get("/admin", handle_admin_root)
    app.router.add_get("/admin/login", handle_login_get)
    app.router.add_post("/admin/login", handle_login_post)
    app.router.add_post("/admin/logout", handle_logout)

    app.router.add_get("/admin/dashboard", handle_dashboard)

    app.router.add_get("/admin/plans", handle_plans)
    app.router.add_post("/admin/plans/add", handle_plans_add)
    app.router.add_post("/admin/plans/{plan_id}/toggle", handle_plan_toggle)

    app.router.add_get("/admin/codes", handle_codes)
    app.router.add_post("/admin/codes/add", handle_codes_add)
    app.router.add_post("/admin/codes/{code_id}/toggle", handle_code_toggle)

    app.router.add_get("/admin/wallet", handle_wallet)
    app.router.add_post("/admin/wallet/{request_id}/approve", handle_wallet_approve)
    app.router.add_post("/admin/wallet/{request_id}/reject", handle_wallet_reject)

    app.router.add_get("/admin/orders", handle_orders)

    app.router.add_get("/admin/settings", handle_settings)
    app.router.add_post("/admin/settings/panel", handle_settings_panel)
    app.router.add_post("/admin/settings/payment", handle_settings_payment)
    app.router.add_post("/admin/settings/forcejoin", handle_settings_forcejoin)
    app.router.add_post("/admin/settings/trial", handle_settings_trial)
    app.router.add_post("/admin/settings/shop", handle_settings_shop)
