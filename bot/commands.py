"""Bot buyruqlari menyusi: oddiy foydalanuvchilar va adminlar uchun alohida."""
import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from .config import get_settings

log = logging.getLogger(__name__)


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash"),
        BotCommand(command="natija", description="Natijamni ko'rish"),
        BotCommand(command="link", description="Shaxsiy taklif havolam"),
    ])
    for admin_id in get_settings().admin_ids:
        await set_admin_commands(bot, admin_id)


async def set_admin_commands(bot: Bot, admin_id: int) -> None:
    try:
        await bot.set_my_commands(
            [BotCommand(command="start", description="Admin panel / reyting"),
             BotCommand(command="link", description="Shaxsiy taklif havolam")],
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    except Exception as e:  # admin hali botga start bosmagan bo'lishi mumkin
        log.warning("Admin %s uchun buyruqlarni o'rnatib bo'lmadi: %s", admin_id, e)


async def reset_commands(bot: Bot, user_id: int) -> None:
    """Adminlikdan chiqqan odamga oddiy foydalanuvchi buyruqlari qaytadi."""
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        log.warning("%s uchun buyruqlarni tiklab bo'lmadi: %s", user_id, e)
