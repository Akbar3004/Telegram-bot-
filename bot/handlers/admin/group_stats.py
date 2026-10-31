"""📈 Guruh statistikasi: a'zolar soni, qo'shilgan va chiqib ketganlar — joriy oy va o'tgan oy taqqoslanadi."""
import logging
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import stats
from .common import NO_GROUP, Menu, back_kb, btn, edit, group_id

log = logging.getLogger(__name__)
router = Router(name="admin_stats")

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def change(cur: float, prev: float) -> str:
    if not prev:
        return ""
    pct = (cur - prev) / prev * 100
    arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➖"
    return f" {arrow} {pct:+.0f}%"


def signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


async def stats_view(bot: Bot, session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    gid = await group_id(session)
    if gid is None:
        return NO_GROUP, back_kb()
    members = None
    try:
        members = await bot.get_chat_member_count(gid)
        await stats.save_snapshot(session, gid, members)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        log.warning("A'zolar sonini olib bo'lmadi: %s", e)

    today = stats.local_today()
    start = stats.month_start(today)
    prev_start = stats.prev_month_start(today)
    cur = await stats.period_stats(session, gid, start, today + timedelta(days=1))
    prev = await stats.period_stats(session, gid, prev_start, start)
    since = await stats.tracking_since(session, gid)

    cur_name, prev_name = MONTHS[today.month - 1], MONTHS[prev_start.month - 1]
    cur_avg, prev_avg = cur.joins / cur.days, prev.joins / prev.days
    lines = [
        "📈 <b>Guruh statistikasi</b>",
        "",
        f"👥 Hozir a'zolar: <b>{members if members is not None else '—'}</b>",
        f"🚪 Kuzatuv boshlanganidan beri chiqib ketganlar: <b>{await stats.total_leaves(session, gid)}</b>",
        "",
        f"<b>📅 {cur_name.capitalize()} (1-{today.day}) va {prev_name} taqqoslanishi:</b>",
        f"➕ Qo'shilganlar: <b>{cur.joins}</b> | {prev.joins}",
        f"➖ Chiqib ketganlar: <b>{cur.leaves}</b> | {prev.leaves}",
        f"📊 Sof o'sish: <b>{signed(cur.net)}</b> | {signed(prev.net)}",
        f"⚡️ Kuniga o'rtacha qo'shilish: <b>{cur_avg:.1f}</b> | {prev_avg:.1f}{change(cur_avg, prev_avg)}",
    ]
    if cur.leaves or prev.leaves:
        cur_lr = cur.leaves / cur.days
        prev_lr = prev.leaves / prev.days
        lines.append(f"🚪 Kuniga o'rtacha chiqish: <b>{cur_lr:.1f}</b> | {prev_lr:.1f}{change(cur_lr, prev_lr)}")
    if cur.members_start is not None and members is not None:
        lines.append(f"👥 Oy boshida: {cur.members_start} → hozir {members} ({signed(members - cur.members_start)})")
    if prev.members_start is not None and cur.members_start is not None:
        lines.append(f"👥 {prev_name.capitalize()} davomida: {prev.members_start} → {cur.members_start} "
                     f"({signed(cur.members_start - prev.members_start)})")
    lines += [
        "",
        "<i>Birinchi son — shu oy, ikkinchisi — o'tgan oy. Joriy oy hali tugamagani uchun taqqoslash "
        "kunlik o'rtacha bo'yicha.</i>",
        "<i>ℹ️ Postlarni nechta odam ko'rgani: Telegram botlarga guruh xabarlarining ko'rishlar sonini bermaydi.</i>",
    ]
    if since:
        lines.append(f"<i>ℹ️ Statistika {since:%d.%m.%Y} dan beri yig'ilmoqda — undan oldingi davr uchun ma'lumot yo'q.</i>")
    else:
        lines.append("<i>ℹ️ Statistika endi yig'ila boshlaydi: har bir kirish va chiqish shu yerda hisoblanadi.</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn("♻️ Yangilash", Menu(action="stats"))]])
    return "\n".join(lines), kb


@router.callback_query(Menu.filter(F.action == "stats"))
async def cb_stats(call: CallbackQuery, bot: Bot, session: AsyncSession) -> None:
    await edit(call, *await stats_view(bot, session))
