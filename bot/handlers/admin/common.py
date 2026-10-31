import html

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
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


def profile_url(user, uid: int) -> str:
    """Profilni ochadigan havola: username bo'lsa t.me/..., bo'lmasa tg://user?id=..."""
    if user is not None and user.username:
        return f"https://t.me/{user.username}"
    return f"tg://user?id={uid}"


def profile_button(user, uid: int, text: str = "💬 Profiliga o'tish") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=profile_url(user, uid))


PRIVACY_NOTE = "\n\n<i>ℹ️ Ba'zi foydalanuvchilarning maxfiylik sozlamasi tufayli profil tugmasi qo'yilmadi — ismiga bosing.</i>"


def strip_tg_buttons(kb: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    if kb is None:
        return None
    rows = [[b for b in row if not (b.url or "").startswith("tg://")] for row in kb.inline_keyboard]
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


async def send_with_fallback(func, text: str, kb: InlineKeyboardMarkup | None):
    """tg://user?id= tugmasini Telegram maxfiylik sababli rad etsa — shunday tugmalarsiz qayta yuboradi."""
    try:
        return await func(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if kb is not None and "PRIVACY" in str(e).upper():
            return await func(text[: 4096 - len(PRIVACY_NOTE)] + PRIVACY_NOTE, reply_markup=strip_tg_buttons(kb))
        raise


async def edit(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        await send_with_fallback(call.message.edit_text, text, kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await send_with_fallback(call.message.answer, text, kb)
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
    left = f" <i>(+{row.added} / −{row.left} chiqqan)</i>" if row.left else ""
    return f"{place_icon(row.place)} {mention(row.user, row.user_id)} — <b>{row.count}</b> ta{left}{wins}"


def short_name(row: repo.RatingRow, limit: int = 22) -> str:
    name = full_name(row.user, row.user_id)
    return name if len(name) <= limit else name[: limit - 1] + "…"


# Admin uchun yozish maydoni ostida doim turadigan ikkita tugma
BTN_CONTEST = "🏆 Konkurs"
BTN_STATS = "📈 Guruh statistikasi"
ADMIN_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_CONTEST), KeyboardButton(text=BTN_STATS)]],
    resize_keyboard=True,
    is_persistent=True,
)


async def main_menu(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    gid = await group_id(session)
    if gid is None:
        return NO_GROUP, InlineKeyboardMarkup(inline_keyboard=[[btn("🔄 Tekshirish", Menu(action="main"))]])
    rnd = await repo.current_round(session, gid)
    rows = await repo.round_rating(session, rnd)
    total = sum(r.count for r in rows)
    lines = [
        "👑 <b>Admin panel</b>",
        f"🔢 Tur: <b>#{rnd.number}</b> ({repo.fmt_dt(repo.to_local(rnd.started_at))} dan)",
        f"👥 Qatnashchilar: <b>{len(rows)}</b> | Hisob jami: <b>{total}</b>",
    ]
    rule = repo.rule_text(rnd)
    if rule:
        winners = repo.winners_by_rule(rnd, rows)
        lines += [rule] + ([f"👑 Shartni bajarganlar: <b>{len(winners)}</b> nafar"] if rnd.win_mode else [])
    lines += ["", "📊 <b>TOP-10 reyting:</b>"]
    lines += [rating_line(r) for r in rows[:10]] or ["<i>Hozircha hech kim odam qo'shmagan.</i>"]
    lines.append("\n<i>🏆 — necha marta g'olib bo'lgani</i>")
    kb = InlineKeyboardBuilder()
    kb.row(btn("📊 To'liq reyting", RatingPage(page=0)), btn("🎁 Mukofot yuborish", PrizeCb(action="start")))
    kb.row(btn("🎯 Konkurs sharti", Menu(action="rules")), btn("👑 G'oliblar (shart)", Menu(action="winners")))
    kb.row(btn("📢 Reytingni guruhga yuborish", Menu(action="post")))
    kb.row(btn("📝 Shablonlar", TplCb(action="list")), btn("🏆 G'oliblar tarixi", Menu(action="history")))
    kb.row(btn("🔄 Yangi tur", Menu(action="newround")), btn("⚙️ Sozlamalar", Menu(action="settings")))
    kb.row(btn("📥 Excel (CSV)", Menu(action="export")), btn("♻️ Yangilash", Menu(action="main")))
    kb.row(btn("👥 Adminlar va egalik", Menu(action="admins")))
    return "\n".join(lines), kb.as_markup()


async def user_card(session: AsyncSession, uid: int) -> tuple[str, InlineKeyboardMarkup]:
    gid = await group_id(session)
    st = await repo.user_stats(session, gid, uid)
    u = st.user
    username = f"@{u.username}" if u and u.username else "yo'q"
    lines = [
        f"👤 {mention(u, uid)}",
        f"🆔 <code>{uid}</code> | {html.escape(username)}",
        "",
        f"📈 Joriy turda: <b>{st.round_count}</b> ta" + (f" — <b>{st.place}-o'rin</b>" if st.place else ""),
        f"📊 Jami qo'shgan: <b>{st.total_count}</b> ta" + (f" (chiqib ketgan: {st.left_count})" if st.left_count else ""),
        f"🔗 Shundan shaxsiy havola orqali: <b>{st.link_count}</b> ta",
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
    kb.row(profile_button(u, uid, "💬 Profiliga o'tib yozish"))
    kb.row(btn("⬅️ Reytingga", RatingPage(page=0)), btn("🏠 Menyu", Menu(action="main")))
    return "\n".join(lines), kb.as_markup()
