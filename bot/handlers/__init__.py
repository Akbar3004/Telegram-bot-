from aiogram import Router

from . import group, user
from .admin import router as admin_router


def setup_routers() -> Router:
    root = Router()
    # Admin routeri birinchi: admin /start bosganda admin panel ochiladi
    root.include_routers(group.router, admin_router, user.router)
    return root
