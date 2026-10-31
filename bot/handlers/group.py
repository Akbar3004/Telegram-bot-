"""Guruhdagi hodisalar: kim kimni qo'shgani, chiqib ketganlar, xizmat xabarlarini o'chirish."""
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import JOIN_TRANSITION, LEAVE_TRANSITION, ChatMemberUpdatedFilter, Command
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import repo
from ..filters import IsAdmin

log = logging.getLogger(__name__)
router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
router.chat_member.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


async def is_target_group(session: AsyncSession, chat_id: int) -> bool:
    return await repo.get_group_id(session, get_settings().group_id) == chat_id


async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        log.warning("Xabarni o'chirib bo'lmadi (bot admin emasmi?): %s", e)


async def bind_group(bot: Bot, session: AsyncSession, chat_id: int, title: str | None, notify_id: int) -> None:
    await repo.set_setting(session, "group_id", str(chat_id))
    await repo.current_round(session, chat_id)
    me = await bot.get_chat_member(chat_id, bot.id)
    warn = ""
    if me.status != "administrator":
        warn = "\n\n⚠️ Bot hali admin emas! Botni admin qiling va <b>xabarlarni o'chirish</b> huquqini bering."
    elif not getattr(me, "can_delete_messages", False):
        warn = "\n\n⚠️ Botga <b>xabarlarni o'chirish</b> huquqini bering."
    try:
        await bot.send_message(
            notify_id, f"✅ Guruh ulandi: <b>{title or chat_id}</b>\nID: <code>{chat_id}</code>{warn}\n\n/start — admin panel"
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


# --- Guruhni ulash ----------------------------------------------------------

@router.message(Command("bind"), IsAdmin())
async def cmd_bind(message: Message, bot: Bot, session: AsyncSession) -> None:
    await safe_delete(message)
    await bind_group(bot, session, message.chat.id, message.chat.title, message.from_user.id)


@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def bot_added(event: ChatMemberUpdated, bot: Bot, session: AsyncSession) -> None:
    """Botni admin guruhga qo'shsa va guruh hali ulanmagan bo'lsa — avtomatik ulanadi."""
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if event.from_user.id not in get_settings().admin_ids:
        return
    if await repo.get_group_id(session, get_settings().group_id) is None:
        await bind_group(bot, session, event.chat.id, event.chat.title, event.from_user.id)


# --- A'zolar qo'shilishi (chat_member update — eng ishonchli manba) -----------

@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def member_joined(event: ChatMemberUpdated, session: AsyncSession) -> None:
    if not await is_target_group(session, event.chat.id):
        return
    member = event.new_chat_member.user
    actor = event.from_user
    await repo.upsert_user(session, member, commit=False)
    await repo.upsert_user(session, actor)
    self_join = (
        actor.id == member.id
        or event.invite_link is not None
        or bool(getattr(event, "via_join_request", False))
        or bool(getattr(event, "via_chat_folder_invite_link", False))
    )
    if member.is_bot or self_join:
        await repo.mark_rejoined(session, event.chat.id, member.id)
        return
    if await repo.record_addition(session, event.chat.id, actor.id, member.id):
        log.info("%s -> %s qo'shdi (chat %s)", actor.id, member.id, event.chat.id)


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def member_left(event: ChatMemberUpdated, session: AsyncSession) -> None:
    if await is_target_group(session, event.chat.id):
        await repo.mark_left(session, event.chat.id, event.new_chat_member.user.id)


# --- Xizmat xabarlari (zaxira manba + o'chirish) ------------------------------

@router.message(F.new_chat_members)
async def new_members_message(message: Message, session: AsyncSession) -> None:
    if not await is_target_group(session, message.chat.id):
        return
    actor = message.from_user
    await repo.upsert_user(session, actor)
    for member in message.new_chat_members:
        await repo.upsert_user(session, member)
        if member.is_bot:
            continue
        if member.id == actor.id:
            await repo.mark_rejoined(session, message.chat.id, member.id)
        else:
            # chat_member update allaqachon yozgan bo'lsa, takror hisoblanmaydi
            await repo.record_addition(session, message.chat.id, actor.id, member.id)
    if await repo.get_flag(session, "delete_service"):
        await safe_delete(message)


@router.message(F.left_chat_member)
async def left_member_message(message: Message, session: AsyncSession) -> None:
    if not await is_target_group(session, message.chat.id):
        return
    await repo.mark_left(session, message.chat.id, message.left_chat_member.id)
    if await repo.get_flag(session, "delete_service"):
        await safe_delete(message)
