import asyncio
import time

from aiogram import Bot

import settings

# Short-lived cache of per-user membership results so that clicking several
# buttons in a row doesn't re-hit the Telegram API (get_chat_member) on every
# single click — this was the main cause of the bot feeling slow, and of
# get_chat_member occasionally failing under load and wrongly blocking users.
_CACHE_TTL = 120  # seconds
_cache: dict[tuple[int, str], tuple[float, bool]] = {}  # (user_id, ch) -> (ts, is_member)


async def _is_member(bot: Bot, channel: str, user_id: int) -> bool:
    key = (user_id, channel)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        is_member = member.status not in ("left", "kicked")
    except Exception:
        # If the bot isn't admin in the channel, or the chat can't be
        # resolved, treat it as "not joined" to be safe — but don't cache
        # transient failures for as long as a real result.
        _cache[key] = (now - _CACHE_TTL + 15, False)
        return False
    _cache[key] = (now, is_member)
    return is_member


async def get_missing_channels(bot: Bot, user_id: int) -> list[str]:
    """Returns the list of required channels the user has NOT joined yet.

    Checks every channel concurrently (instead of one-by-one) and caches
    results briefly per user so repeated clicks stay fast.
    """
    channels = await settings.get_list("FORCE_JOIN_CHANNELS")
    if not channels:
        return []
    results = await asyncio.gather(*(_is_member(bot, ch, user_id) for ch in channels))
    return [ch for ch, ok in zip(channels, results) if not ok]
