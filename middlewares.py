from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import keyboards as kb
import settings
from membership import get_missing_channels


class ForceJoinMiddleware(BaseMiddleware):
    """Blocks every update until the user has joined all required channels."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        channels = await settings.get_list("FORCE_JOIN_CHANNELS")
        if not channels:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Admins are never blocked by their own force-join setting — otherwise
        # a misconfigured channel (bot not admin there, wrong username, ...)
        # would lock the admin out of their own admin panel.
        if await settings.is_admin(user.id):
            return await handler(event, data)

        # Let the "check_join" button itself reach its handler.
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            return await handler(event, data)

        bot = data["bot"]
        missing = await get_missing_channels(bot, user.id)
        if not missing:
            return await handler(event, data)

        text = "⛔️ برای ادامه، ابتدا باید عضو کانال(های) زیر بشی:"
        if isinstance(event, Message):
            await event.answer(text, reply_markup=await kb.join_channels_kb())
        elif isinstance(event, CallbackQuery):
            await event.answer("ابتدا باید عضو کانال‌ها بشی ❌", show_alert=True)
            await event.message.answer(text, reply_markup=await kb.join_channels_kb())
        return None
