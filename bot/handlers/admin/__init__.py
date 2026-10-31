from aiogram import F, Router
from aiogram.enums import ChatType

from ...filters import IsAdmin
from . import contest, group_stats, menu, owner, prize, templates

router = Router(name="admin")
for obs in (router.message, router.callback_query):
    obs.filter(IsAdmin())
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.include_routers(menu.router, owner.router, group_stats.router, contest.router, templates.router, prize.router)
