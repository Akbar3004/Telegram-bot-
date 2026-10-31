"""Bot va Dispatcher yaratish — polling (server/Docker) va webhook (Vercel) uchun umumiy."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from .config import get_settings
from .db.fsm_storage import DbStorage
from .handlers import setup_routers
from .middlewares import DbSessionMiddleware

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        get_settings().bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=DbStorage())
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.include_router(setup_routers())
    return dp


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash"),
        BotCommand(command="natija", description="Natijamni ko'rish"),
        BotCommand(command="link", description="Shaxsiy taklif havolam"),
    ])
    for admin_id in get_settings().admin_ids:
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description="Admin panel / reyting"),
                 BotCommand(command="link", description="Shaxsiy taklif havolam")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:  # admin hali botga start bosmagan bo'lishi mumkin
            log.warning("Admin %s uchun buyruqlarni o'rnatib bo'lmadi: %s", admin_id, e)
