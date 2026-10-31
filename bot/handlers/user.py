"""Oddiy foydalanuvchilar uchun: o'z natijasi va shaxsiy taklif havolasi."""
import html
import logging
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import repo
from ..utils import full_name

log = logging.getLogger(__name__)
router = Router(name="user")
router.message.filter(F.chat.type == ChatType.PRIVATE)

USER_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔗 Shaxsiy taklif havolam", callback_data="mylink")],
    [InlineKeyboardButton(text="🔄 Yangilash", callback_data="me")],
])


async def my_stats_text(session: AsyncSession, user_id: int) -> str:
    gid = await repo.get_group_id(session, get_settings().group_id)
    if gid is None:
        return "Konkurs hali boshlanmagan."
    st = await repo.user_stats(session, gid, user_id)
    rnd = await repo.current_round(session, gid)
    place = f"{st.place}-o'rin" if st.place else "hali reytingda yo'qsiz"
    text = (
        f"📊 <b>Sizning natijangiz</b> (tur #{rnd.number})\n\n"
        f"👥 Qo'shgan odamlaringiz: <b>{st.round_count}</b> ta\n"
        f"🏅 Reytingdagi o'rningiz: <b>{place}</b>\n"
        f"🏆 G'olib bo'lganingiz: <b>{st.wins}</b> marta"
    )
    if st.left_count:
        text += f"\n\nℹ️ Siz qo'shganlardan {st.left_count} tasi guruhdan chiqib ketgan."
    return text + "\n\nGuruhga ko'proq do'stlaringizni qo'shing va g'olib bo'ling! 🚀"


async def get_or_create_link(bot: Bot, session: AsyncSession, gid: int, user) -> str | None:
    link = await repo.get_invite_link(session, gid, user.id)
    if link:
        return link
    try:
        # Havola nomi adminlarga guruh sozlamalarida kimniki ekanini ko'rsatadi (maks. 32 belgi)
        name = f"{full_name(await session.get(repo.User, user.id), user.id)[:18]} #{user.id}"[:32]
        invite = await bot.create_chat_invite_link(gid, name=name)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        log.warning("Taklif havolasini yaratib bo'lmadi (botda 'Foydalanuvchilarni taklif qilish' huquqi bormi?): %s", e)
        return None
    await repo.save_invite_link(session, gid, user.id, invite.invite_link)
    return invite.invite_link


async def send_link(target: Message, bot: Bot, session: AsyncSession, user) -> None:
    gid = await repo.get_group_id(session, get_settings().group_id)
    if gid is None:
        await target.answer("Konkurs hali boshlanmagan.")
        return
    await repo.upsert_user(session, user, started=True)
    link = await get_or_create_link(bot, session, gid, user)
    if link is None:
        await target.answer("😔 Hozircha havola yaratib bo'lmadi. Iltimos, keyinroq urinib ko'ring yoki adminga murojaat qiling.")
        return
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('Guruhimizga qo‘shiling! 👇')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", url=share)],
        [InlineKeyboardButton(text="📊 Natijam", callback_data="me")],
    ])
    await target.answer(
        "🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n\n"
        f"{html.escape(link)}\n\n"
        "Shu havola orqali guruhga kirgan har bir odam <b>sizga hisoblanadi</b>. "
        "Uni do'stlaringizga yuboring yoki boshqa guruh va kanallarda ulashing.\n\n"
        "💡 Odamlarni guruhga o'zingiz qo'shsangiz ham hisoblanadi.",
        reply_markup=kb,
    )


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot, session: AsyncSession) -> None:
    await repo.upsert_user(session, message.from_user, started=True)
    if command.args == "link":
        await send_link(message, bot, session, message.from_user)
        return
    await message.answer(
        "Assalomu alaykum! 👋\nMen guruhga eng ko'p odam qo'shganlarni hisoblovchi botman. "
        "Mukofotlar haqidagi xabarlar shu yerga keladi.\n\n" + await my_stats_text(session, message.from_user.id),
        reply_markup=USER_KB,
    )


@router.message(Command("link"))
async def cmd_link(message: Message, bot: Bot, session: AsyncSession) -> None:
    await send_link(message, bot, session, message.from_user)


@router.callback_query(F.data == "mylink")
async def cb_link(call: CallbackQuery, bot: Bot, session: AsyncSession) -> None:
    await call.answer()
    await send_link(call.message, bot, session, call.from_user)


@router.callback_query(F.data == "me")
async def refresh(call: CallbackQuery, session: AsyncSession) -> None:
    try:
        await call.message.edit_text(await my_stats_text(session, call.from_user.id), reply_markup=USER_KB)
    except TelegramBadRequest:
        await call.message.answer(await my_stats_text(session, call.from_user.id), reply_markup=USER_KB)
    await call.answer("Yangilandi")


@router.my_chat_member(F.chat.type == ChatType.PRIVATE, ChatMemberUpdatedFilter(KICKED))
async def blocked(event: ChatMemberUpdated, session: AsyncSession) -> None:
    await repo.set_started(session, event.from_user.id, False)


@router.my_chat_member(F.chat.type == ChatType.PRIVATE, ChatMemberUpdatedFilter(MEMBER))
async def unblocked(event: ChatMemberUpdated, session: AsyncSession) -> None:
    await repo.upsert_user(session, event.from_user, started=True)
