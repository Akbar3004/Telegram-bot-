"""Guruhdagi hodisalar: kim kimni qo'shgani, chiqib ketganlar, xizmat xabarlarini o'chirish."""
import logging
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import JOIN_TRANSITION, LEAVE_TRANSITION, ChatMemberUpdatedFilter, Command
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import board
from ..config import get_settings
from ..db import repo, stats
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
    else:
        missing = [name for attr, name in (("can_delete_messages", "xabarlarni o'chirish"),
                                           ("can_invite_users", "foydalanuvchilarni taklif qilish (havolalar uchun)"))
                   if not getattr(me, attr, False)]
        if missing:
            warn = "\n\n⚠️ Botga quyidagi huquqlarni bering: <b>" + ", ".join(missing) + "</b>"
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
    if not await repo.is_admin(session, event.from_user.id, get_settings().admin_ids):
        return
    if await repo.get_group_id(session, get_settings().group_id) is None:
        await bind_group(bot, session, event.chat.id, event.chat.title, event.from_user.id)


# --- A'zolar qo'shilishi (chat_member update — eng ishonchli manba) -----------

async def track(bot: Bot, session: AsyncSession, chat_id: int, user_id: int, kind: str) -> None:
    """Statistika: kirish/chiqishni yozadi va a'zolar sonini kuniga bir marta saqlaydi."""
    await stats.record_event(session, chat_id, user_id, kind)
    if not await stats.has_snapshot_today(session, chat_id):
        try:
            await stats.save_snapshot(session, chat_id, await bot.get_chat_member_count(chat_id))
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            log.warning("A'zolar sonini olib bo'lmadi: %s", e)


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def member_joined(event: ChatMemberUpdated, bot: Bot, session: AsyncSession) -> None:
    if not await is_target_group(session, event.chat.id):
        return
    member = event.new_chat_member.user
    actor = event.from_user
    await repo.upsert_user(session, member, commit=False)
    await repo.upsert_user(session, actor)
    if member.is_bot:
        return
    await track(bot, session, event.chat.id, member.id, "join")
    # Shaxsiy taklif havolasi orqali kirgan bo'lsa — havola egasiga hisoblanadi
    if event.invite_link is not None:
        owner = await repo.link_owner(session, event.chat.id, event.invite_link.invite_link)
        if owner is not None:
            if await repo.record_addition(session, event.chat.id, owner, member.id, source="link"):
                log.info("%s havolasi orqali %s kirdi (chat %s)", owner, member.id, event.chat.id)
            else:
                await repo.mark_rejoined(session, event.chat.id, member.id)
            return
    self_join = (
        actor.id == member.id
        or event.invite_link is not None
        or bool(getattr(event, "via_join_request", False))
        or bool(getattr(event, "via_chat_folder_invite_link", False))
    )
    if self_join:
        await repo.mark_rejoined(session, event.chat.id, member.id)
        return
    if await repo.record_addition(session, event.chat.id, actor.id, member.id):
        log.info("%s -> %s qo'shdi (chat %s)", actor.id, member.id, event.chat.id)


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def member_left(event: ChatMemberUpdated, bot: Bot, session: AsyncSession) -> None:
    if await is_target_group(session, event.chat.id):
        await repo.mark_left(session, event.chat.id, event.new_chat_member.user.id)
        if not event.new_chat_member.user.is_bot:
            await track(bot, session, event.chat.id, event.new_chat_member.user.id, "leave")


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


# --- /top — reytingni guruhda hammaga ko'rsatish ---------------------------

TOP_SIZE = 10
TOP_COOLDOWN = 60  # soniya: guruhni /top bilan spam qilib bo'lmasin


async def result_buttons(bot: Bot) -> InlineKeyboardMarkup:
    """Guruhdagi reyting xabarlari ostidagi tugmalar: botda o'z natijasini va havolasini olish."""
    me = await bot.me()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Natijamni ko'rish", url=f"https://t.me/{me.username}?start=me")],
        [InlineKeyboardButton(text="🔗 Shaxsiy havolamni olish", url=f"https://t.me/{me.username}?start=link")],
    ])


@router.message(Command("top"))
async def cmd_top(message: Message, bot: Bot, session: AsyncSession) -> None:
    if not await is_target_group(session, message.chat.id):
        return
    await safe_delete(message)
    if not await repo.get_flag(session, "top_enabled"):
        return
    # Oxirgi vaqt bazada saqlanadi — serverless (Vercel) muhitida xotira so'rovlar orasida saqlanmaydi
    now = time.time()
    if now - float(await repo.get_setting(session, "last_top_at") or 0) < TOP_COOLDOWN:
        return
    await repo.set_setting(session, "last_top_at", str(now))

    rnd = await repo.current_round(session, message.chat.id)
    rows = await repo.round_rating(session, rnd)
    ids = {r.user_id for r in repo.winners_by_rule(rnd, rows)}
    lines = board.header(rnd, f"🏆 <b>TOP-{TOP_SIZE} — eng ko'p odam qo'shganlar</b>")
    lines += [board.row_line(r, ids) for r in rows[:TOP_SIZE]]
    if not rows:
        lines.append("<i>Hozircha hech kim odam qo'shmagan. Birinchi bo'ling!</i>")
    lines.append("\n👇 O'z natijangiz va shaxsiy taklif havolangizni botdan oling")
    kb = await result_buttons(bot)

    # Eski /top xabarini o'chiramiz — guruhda faqat eng oxirgisi qoladi
    old = await repo.get_setting(session, "last_top_msg")
    if old:
        try:
            await bot.delete_message(message.chat.id, int(old))
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
    sent = await bot.send_message(message.chat.id, "\n".join(lines), reply_markup=kb)
    await repo.set_setting(session, "last_top_msg", str(sent.message_id))
