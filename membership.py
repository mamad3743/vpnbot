from aiogram import Bot

import settings


async def get_missing_channels(bot: Bot, user_id: int) -> list[str]:
    """Returns the list of required channels the user has NOT joined yet."""
    channels = await settings.get_list("FORCE_JOIN_CHANNELS")
    missing: list[str] = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            # If the bot isn't admin in the channel, or the chat can't be
            # resolved, treat it as "not joined" to be safe.
            missing.append(ch)
    return missing
