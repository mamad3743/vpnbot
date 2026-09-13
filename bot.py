import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from middlewares import ForceJoinMiddleware
from handlers import admin, orders, plans, start, trial, wallet


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده. آن را در متغیرهای محیطی (Environment Variables) قرار بده.")

    await db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # Order matters: start.router is first so the global /cancel handler
    # always takes priority over state-specific handlers in other routers.
    dp.include_router(start.router)
    dp.include_router(plans.router)
    dp.include_router(trial.router)
    dp.include_router(wallet.router)
    dp.include_router(orders.router)
    dp.include_router(admin.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started, polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
