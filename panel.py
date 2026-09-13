"""
Thin wrapper around the official `pasarguard` async python client.
Handles admin-token caching and exposes one simple helper used by the bot:
create_vpn_user(...) -> (panel_username, subscription_link)

If your panel's exact method names differ (panel versions evolve), check
your own instance's Swagger docs at <PANEL_URL>/docs and adjust the calls
in create_vpn_user() below.
"""

import time
from typing import Optional

from pasarguard import PasarguardAPI, Tools, UserCreate, UserStatus

import config

_api: Optional[PasarguardAPI] = None
_token: Optional[str] = None
_token_fetched_at: float = 0.0
TOKEN_TTL_SECONDS = 50 * 60  # refresh a bit before the panel's ~1h token expiry


def get_api() -> PasarguardAPI:
    global _api
    if _api is None:
        if not config.PANEL_URL:
            raise RuntimeError("PANEL_URL تنظیم نشده است.")
        _api = PasarguardAPI(base_url=config.PANEL_URL, timeout=20.0, verify=True)
    return _api


async def get_valid_token() -> str:
    global _token, _token_fetched_at
    if _token is None or (time.time() - _token_fetched_at) > TOKEN_TTL_SECONDS:
        result = await get_api().get_token(
            username=config.PANEL_USERNAME,
            password=config.PANEL_PASSWORD,
        )
        _token = result.access_token
        _token_fetched_at = time.time()
    return _token


async def create_vpn_user(username: str, days: int, gb: int, note: str = "") -> tuple[str, str]:
    """Create a user on the PasarGuard panel.

    Returns (panel_username, subscription_url).
    """
    token = await get_valid_token()
    payload = UserCreate(
        username=username,
        data_limit=Tools.gb(gb) if gb else 0,
        expire=Tools.days(days),
        status=UserStatus.ACTIVE,
        group_ids=config.PANEL_GROUP_IDS,
        note=note,
    )

    api = get_api()
    if config.PANEL_GROUP_IDS:
        user = await api.create_user(payload, token=token)
    else:
        # No specific group configured -> add the user to every group on the panel
        user = await api.create_user_in_all_groups(payload, token=token)

    return user.username, user.subscription_url
