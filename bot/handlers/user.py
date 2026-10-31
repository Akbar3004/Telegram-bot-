"""Oddiy foydalanuvchilar uchun: o'z natijasini ko'rish."""
from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import repo

router = Router(name="user")
router.message.filter(F.chat.type == ChatType.PRIVATE)

REFRESH_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Yangilash", callback_data="me")]])


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


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession) -> None:
    await repo.upsert_user(session, message.from_user, started=True)
    await message.answer(
        "Assalomu alaykum! 👋\nMen guruhga eng ko'p odam qo'shganlarni hisoblovchi botman. "
        "Mukofotlar haqidagi xabarlar shu yerga keladi.\n\n" + await my_stats_text(session, message.from_user.id),
        reply_markup=REFRESH_KB,
    )


@router.callback_query(F.data == "me")
async def refresh(call: CallbackQuery, session: AsyncSession) -> None:
    try:
        await call.message.edit_text(await my_stats_text(session, call.from_user.id), reply_markup=REFRESH_KB)
    except TelegramBadRequest:
        pass
    await call.answer("Yangilandi")


@router.my_chat_member(F.chat.type == ChatType.PRIVATE, ChatMemberUpdatedFilter(KICKED))
async def blocked(event: ChatMemberUpdated, session: AsyncSession) -> None:
    await repo.set_started(session, event.from_user.id, False)


@router.my_chat_member(F.chat.type == ChatType.PRIVATE, ChatMemberUpdatedFilter(MEMBER))
async def unblocked(event: ChatMemberUpdated, session: AsyncSession) -> None:
    await repo.upsert_user(session, event.from_user, started=True)
