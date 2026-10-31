"""Bot va Dispatcher yaratish — polling (server/Docker) va webhook (Vercel) uchun umumiy."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .commands import setup_bot_commands  # noqa: F401 (webhook.py va __main__ shu yerdan oladi)
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
