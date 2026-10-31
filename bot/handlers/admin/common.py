import html

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db import repo
from ...utils import full_name, mention, place_icon

PAGE_SIZE = 10


class Menu(CallbackData, prefix="m"):
    action: str


class RatingPage(CallbackData, prefix="rp"):
    page: int


class UserCb(CallbackData, prefix="u"):
    action: str
    uid: int


class TplCb(CallbackData, prefix="t"):
    action: str
    tid: int = 0


class PrizeCb(CallbackData, prefix="p"):
    action: str
    value: int = 0


def btn(text: str, cb: CallbackData | str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb if isinstance(cb, str) else cb.pack())


def back_kb(to: CallbackData | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[btn("⬅️ Orqaga", to or Menu(action="main"))]])


async def edit(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await call.message.answer(text, reply_markup=kb)
    await call.answer()


async def group_id(session: AsyncSession) -> int | None:
    return await repo.get_group_id(session, get_settings().group_id)


NO_GROUP = (
    "⚠️ <b>Guruh ulanmagan.</b>\n\n"
    "1. Botni guruhga qo'shing va <b>admin</b> qiling (xabarlarni o'chirish huquqi bilan).\n"
    "2. Guruhda <code>/bind</code> deb yozing.\n\n"
    "Shundan so'ng bot kim nechta odam qo'shganini hisoblay boshlaydi."
)


def rating_line(row: repo.RatingRow) -> str:
    wins = f" | 🏆 {row.wins}" if row.wins else ""
    return f"{place_icon(row.place)} {mention(row.user, row.user_id)} — <b>{row.count}</b> ta{wins}"


def short_name(row: repo.RatingRow, limit: int = 22) -> str:
    name = full_name(row.user, row.user_id)
    return name if len(name) <= limit else name[: limit - 1] + "…"


async def main_menu(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    gid = await group_id(session)
    if gid is None:
        return NO_GROUP, InlineKeyboardMarkup(inline_keyboard=[[btn("🔄 Tekshirish", Menu(action="main"))]])
    rnd = await repo.current_round(session, gid)
    rows = await repo.rating(session, rnd.id, await repo.get_flag(session, "subtract_left"))
    total = sum(r.count for r in rows)
    lines = [
        "👑 <b>Admin panel</b>",
        f"🔢 Tur: <b>#{rnd.number}</b> ({repo.fmt_dt(rnd.started_at)} dan)",
        f"👥 Qatnashchilar: <b>{len(rows)}</b> | Qo'shilganlar: <b>{total}</b>",
        "",
        "📊 <b>TOP-10 reyting:</b>",
    ]
    lines += [rating_line(r) for r in rows[:10]] or ["<i>Hozircha hech kim odam qo'shmagan.</i>"]
    lines.append("\n<i>🏆 — necha marta g'olib bo'lgani</i>")
    kb = InlineKeyboardBuilder()
    kb.row(btn("📊 To'liq reyting", RatingPage(page=0)), btn("🎁 Mukofot yuborish", PrizeCb(action="start")))
    kb.row(btn("📝 Shablonlar", TplCb(action="list")), btn("🏆 G'oliblar tarixi", Menu(action="history")))
    kb.row(btn("🔄 Yangi tur", Menu(action="newround")), btn("⚙️ Sozlamalar", Menu(action="settings")))
    kb.row(btn("📥 Excel (CSV)", Menu(action="export")), btn("♻️ Yangilash", Menu(action="main")))
    return "\n".join(lines), kb.as_markup()


async def user_card(session: AsyncSession, uid: int) -> tuple[str, InlineKeyboardMarkup]:
    gid = await group_id(session)
    st = await repo.user_stats(session, gid, uid)
    u = st.user
    username = f"@{u.username}" if u and u.username else "yo'q"
    lines = [
        f"👤 {mention(u, uid)}  <i>(ismga bosing — profil ochiladi)</i>",
        f"🆔 <code>{uid}</code> | {html.escape(username)}",
        "",
        f"📈 Joriy turda: <b>{st.round_count}</b> ta" + (f" — <b>{st.place}-o'rin</b>" if st.place else ""),
        f"📊 Jami qo'shgan: <b>{st.total_count}</b> ta" + (f" (chiqib ketgan: {st.left_count})" if st.left_count else ""),
        f"🏆 G'olib bo'lgan: <b>{st.wins}</b> marta" + (" (shu turda ✅)" if st.won_this_round else ""),
        "🤖 Botga start bosgan: " + ("✅ ha" if u and u.started_bot else "❌ yo'q — bot unga yozolmaydi, profiliga kirib o'zingiz yozing"),
    ]
    kb = InlineKeyboardBuilder()
    kb.row(btn("✉️ Bot orqali yozish", UserCb(action="write", uid=uid)), btn("🎁 Shablon yuborish", UserCb(action="tpl", uid=uid)))
    if st.won_this_round:
        kb.row(btn("❌ G'oliblikdan olib tashlash", UserCb(action="unwin", uid=uid)))
    else:
        kb.row(btn("🏆 G'olib deb belgilash", UserCb(action="win", uid=uid)))
    kb.row(btn("👥 Kimlarni qo'shgan", UserCb(action="members", uid=uid)))
    if u and u.username:
        kb.row(InlineKeyboardButton(text="💬 Profilga o'tish", url=f"https://t.me/{u.username}"))
    kb.row(btn("⬅️ Reytingga", RatingPage(page=0)), btn("🏠 Menyu", Menu(action="main")))
    return "\n".join(lines), kb.as_markup()
