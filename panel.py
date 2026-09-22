"""
Thin wrapper around the official `pasarguard` async python client.
Reads panel URL/credentials from the live `settings` table (editable from
the bot's admin panel) instead of static env vars, and re-creates the API
client automatically whenever the panel URL changes.

Two auth modes are supported (chosen automatically):
  - PANEL_API_TOKEN set  -> used directly as the bearer token, no login call.
  - otherwise            -> PANEL_USERNAME/PANEL_PASSWORD login via get_token(),
                             cached and refreshed automatically.

If your panel's exact method names differ (panel versions evolve), check
your own instance's Swagger docs at <PANEL_URL>/docs and adjust the calls
in create_vpn_user() below.
"""

import time
from typing import Optional

from pasarguard import PasarguardAPI, Tools, UserCreate, UserStatus

import settings

_api: Optional[PasarguardAPI] = None
_api_base_url: Optional[str] = None
_token: Optional[str] = None
_token_fetched_at: float = 0.0
TOKEN_TTL_SECONDS = 50 * 60  # refresh a bit before the panel's ~1h token expiry


async def get_api() -> PasarguardAPI:
    global _api, _api_base_url, _token
    base_url = (await settings.get("PANEL_URL", "")).rstrip("/")
    if not base_url:
        raise RuntimeError("آدرس پنل (PANEL_URL) هنوز از پنل مدیریت تنظیم نشده.")
    if _api is None or _api_base_url != base_url:
        _api = PasarguardAPI(base_url=base_url, timeout=20.0, verify=True)
        _api_base_url = base_url
        _token = None  # force re-login on a new panel
    return _api


async def get_valid_token() -> str:
    global _token, _token_fetched_at

    # Mode 1: static API token entered by the admin — used as-is, no login call.
    api_token = await settings.get("PANEL_API_TOKEN", "")
    if api_token:
        return api_token

    # Mode 2: username/password login, cached until it's close to expiring.
    api = await get_api()
    if _token is None or (time.time() - _token_fetched_at) > TOKEN_TTL_SECONDS:
        username = await settings.get("PANEL_USERNAME", "")
        password = await settings.get("PANEL_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "نه توکن API و نه یوزرنیم/پسورد پنل تنظیم نشده. از پنل مدیریت تنظیمش کن."
            )
        result = await api.get_token(username=username, password=password)
        _token = result.access_token
        _token_fetched_at = time.time()
    return _token


async def create_vpn_user(
    username: str,
    note: str = "",
    days: Optional[int] = None,
    gb: Optional[int] = None,
    minutes: Optional[int] = None,
    mb: Optional[int] = None,
) -> tuple[str, str]:
    """Create a user on the PasarGuard panel.

    Duration can be given as days OR minutes (minutes wins if both are
    given); data limit as gb OR mb (mb wins if both are given). This lets
    trial accounts use fine-grained "600MB for 1 hour" style limits while
    paid plans keep using whole days/GB.

    Returns (panel_username, subscription_url).
    """
    api = await get_api()
    token = await get_valid_token()
    group_ids = await settings.get_list("PANEL_GROUP_IDS")
    group_ids_int = [int(g) for g in group_ids] if group_ids else None

    if minutes is not None:
        expire = Tools.minutes(minutes)
    else:
        expire = Tools.days(days or 0)

    if mb is not None:
        data_limit = Tools.mb(mb)
    elif gb:
        data_limit = Tools.gb(gb)
    else:
        data_limit = 0

    payload = UserCreate(
        username=username,
        data_limit=data_limit,
        expire=expire,
        status=UserStatus.ACTIVE,
        group_ids=group_ids_int,
        note=note,
    )

    if group_ids_int:
        user = await api.create_user(payload, token=token)
    else:
        # No specific group configured -> add the user to every group on the panel
        user = await api.create_user_in_all_groups(payload, token=token)

    return user.username, user.subscription_url
