from aiogram import F, Router
from aiogram.enums import ChatType

from ...filters import IsAdmin
from . import ai_post, contest, menu, prize, templates

router = Router(name="admin")
for obs in (router.message, router.callback_query):
    obs.filter(IsAdmin())
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.include_routers(menu.router, contest.router, templates.router, prize.router, ai_post.router)
