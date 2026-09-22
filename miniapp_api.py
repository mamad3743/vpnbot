import hashlib
import hmac
import json
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

import database as db
import settings

MINIAPP_DIR = Path(__file__).parent / "miniapp"


def _validate_init_data(bot_token: str, init_data: str) -> dict | None:
    """Verifies the signature Telegram attaches to WebApp.initData and
    returns the parsed `user` dict on success, or None if invalid/missing."""
    if not bot_token or not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(key=b"WebAppData", msg=bot_token.encode(), digestmod=hashlib.sha256).digest()
    calculated_hash = hmac.new(
        key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256
    ).hexdigest()

    if calculated_hash != received_hash:
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except Exception:
        return None


async def handle_miniapp_index(request: web.Request) -> web.Response:
    index_path = MINIAPP_DIR / "index.html"
    return web.Response(text=index_path.read_text(encoding="utf-8"), content_type="text/html")


async def handle_api_config(request: web.Request) -> web.Response:
    theme = await settings.get("MINIAPP_THEME", "ocean")
    accent = await settings.get("MINIAPP_ACCENT", "#2f80ed")  # only used when theme == "custom"
    currency = await settings.get("CURRENCY", "تومان")
    shop_name = await settings.get("SHOP_NAME", "فروشگاه VPN")
    trial_minutes = await settings.get_int("TRIAL_MINUTES", 60)
    trial_mb = await settings.get_int("TRIAL_MB", 600)
    return web.json_response(
        {
            "theme": theme,
            "accent": accent,
            "currency": currency,
            "shop_name": shop_name,
            "trial_minutes": trial_minutes,
            "trial_mb": trial_mb,
        }
    )


async def handle_api_plans(request: web.Request) -> web.Response:
    plans = await db.list_plans()
    return web.json_response(
        [
            {
                "id": p["id"],
                "title": p["title"],
                "gb": p["gb"],
                "days": p["days"],
                "price": p["price"],
                "color": p["color"] or "",
            }
            for p in plans
        ]
    )


async def handle_api_me(request: web.Request) -> web.Response:
    init_data = request.query.get("initData", "")
    bot_token = await settings.get("BOT_TOKEN", "")
    user = _validate_init_data(bot_token, init_data)
    if not user:
        return web.json_response({"valid": False}, status=401)

    user_id = user.get("id")
    await db.ensure_user(user_id, user.get("username"))
    balance = await db.get_wallet_balance(user_id)
    used_trial = await db.has_used_trial(user_id)

    return web.json_response(
        {
            "valid": True,
            "user_id": user_id,
            "balance": balance,
            "used_trial": used_trial,
        }
    )


def register_routes(app: web.Application) -> None:
    app.router.add_get("/miniapp/", handle_miniapp_index)
    app.router.add_get("/miniapp/index.html", handle_miniapp_index)
    app.router.add_get("/api/config", handle_api_config)
    app.router.add_get("/api/plans", handle_api_plans)
    app.router.add_get("/api/me", handle_api_me)
