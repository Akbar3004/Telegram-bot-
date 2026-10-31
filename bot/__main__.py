import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from .config import get_settings
from .db.session import init_db, make_engine
from .handlers import setup_routers
from .middlewares import DbSessionMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    sessionmaker = await init_db(make_engine(settings.database_url))

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(setup_routers())

    await bot.set_my_commands([BotCommand(command="start", description="Natijamni ko'rish")])
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description="Admin panel / reyting")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # admin hali botga start bosmagan bo'lishi mumkin
            pass

    # chat_member yangilanishlari faqat aniq so'ralganda keladi — shuning uchun resolve_used_update_types
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
