"""
All business-configurable values (panel credentials, force-join channels, card
info, trial size, mini-app theme, etc.) live in the `settings` table and are
edited live from the in-bot admin panel — no redeploy or Railway variables
needed. Only a couple of bootstrap values (PORT, DB_PATH) come from the
process environment because they have to exist before the database does.

A tiny in-memory cache sits in front of the DB so hot-path reads (e.g. on
every incoming message) don't hit SQLite every time.
"""

from typing import Optional

import database as db

_cache: dict[str, str] = {}
_loaded = False


async def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        _cache.update(await db.get_all_settings_raw())
        _loaded = True


async def get(key: str, default: str = "") -> str:
    await _ensure_loaded()
    return _cache.get(key, default)


async def set(key: str, value: str) -> None:
    await _ensure_loaded()
    _cache[key] = value
    await db.set_setting_raw(key, value)


async def get_int(key: str, default: int = 0) -> int:
    raw = await get(key, "")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


async def get_list(key: str, default: Optional[list[str]] = None) -> list[str]:
    raw = await get(key, "")
    if not raw:
        return default or []
    return [x.strip() for x in raw.split(",") if x.strip()]


async def set_list(key: str, values: list[str]) -> None:
    await set(key, ",".join(v.strip() for v in values if v.strip()))


async def get_bool(key: str, default: bool = False) -> bool:
    raw = await get(key, "")
    if raw == "":
        return default
    return raw == "1"


async def set_bool(key: str, value: bool) -> None:
    await set(key, "1" if value else "0")


async def is_installed() -> bool:
    return await get_bool("INSTALLED", False)


async def get_admin_ids() -> list[int]:
    raw = await get_list("ADMIN_IDS")
    out = []
    for x in raw:
        try:
            out.append(int(x))
        except ValueError:
            pass
    return out


async def is_admin(user_id: int) -> bool:
    return user_id in await get_admin_ids()
