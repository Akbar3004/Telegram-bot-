from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import repo


class IsAdmin(BaseFilter):
    """Ega, bazadagi yordamchi adminlar yoki ADMIN_IDS (Vercel) dagi super-adminlar."""

    async def __call__(self, event: Message | CallbackQuery, session: AsyncSession) -> bool:
        return bool(event.from_user) and await repo.is_admin(session, event.from_user.id, get_settings().admin_ids)
