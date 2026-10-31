"""Server yoki Docker'da polling rejimida ishga tushirish: python -m bot"""
import asyncio
import logging

from .app import create_bot, create_dispatcher, setup_bot_commands
from .config import get_settings
from .db.session import init_db, make_engine


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await init_db(make_engine(get_settings().database_url))
    bot = create_bot()
    dp = create_dispatcher()
    await setup_bot_commands(bot)
    # Agar avval Vercel uchun webhook o'rnatilgan bo'lsa — polling ishlashi uchun olib tashlaymiz
    await bot.delete_webhook()
    # chat_member yangilanishlari faqat aniq so'ralganda keladi — shuning uchun resolve_used_update_types
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
