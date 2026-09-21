"""
Thin wrapper around the official `pasarguard` async python client.
Reads panel URL/credentials from the live `settings` table (editable from
the bot's admin panel) instead of static env vars, and re-creates the API
client automatically whenever the panel URL changes.

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
    api = await get_api()
    if _token is None or (time.time() - _token_fetched_at) > TOKEN_TTL_SECONDS:
        username = await settings.get("PANEL_USERNAME", "")
        password = await settings.get("PANEL_PASSWORD", "")
        result = await api.get_token(username=username, password=password)
        _token = result.access_token
        _token_fetched_at = time.time()
    return _token


async def create_vpn_user(username: str, days: int, gb: int, note: str = "") -> tuple[str, str]:
    """Create a user on the PasarGuard panel.

    Returns (panel_username, subscription_url).
    """
    api = await get_api()
    token = await get_valid_token()
    group_ids = await settings.get_list("PANEL_GROUP_IDS")
    group_ids_int = [int(g) for g in group_ids] if group_ids else None

    payload = UserCreate(
        username=username,
        data_limit=Tools.gb(gb) if gb else 0,
        expire=Tools.days(days),
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
