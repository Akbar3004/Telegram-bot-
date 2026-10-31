import csv
import io

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import repo
from ...db.models import Win
from ...utils import full_name, mention
from .common import (
    NO_GROUP, PAGE_SIZE, Menu, RatingPage, UserCb, back_kb, btn, edit, group_id, main_menu,
    profile_button, rating_line, short_name, user_card,
)

router = Router(name="admin_menu")


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await repo.upsert_user(session, message.from_user, started=True)
    text, kb = await main_menu(session)
    await message.answer(text, reply_markup=kb)


@router.callback_query(Menu.filter(F.action == "main"))
async def cb_main(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    text, kb = await main_menu(session)
    await edit(call, text, kb)


# --- Reyting ----------------------------------------------------------------

@router.callback_query(RatingPage.filter())
async def cb_rating(call: CallbackQuery, callback_data: RatingPage, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    rnd = await repo.current_round(session, gid)
    rows = await repo.rating(session, rnd.id, await repo.get_flag(session, "subtract_left"))
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(max(callback_data.page, 0), pages - 1)
    chunk = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    lines = [f"📊 <b>Reyting — tur #{rnd.number}</b> (sahifa {page + 1}/{pages})", ""]
    lines += [rating_line(r) for r in chunk] or ["<i>Hozircha bo'sh.</i>"]
    lines.append("\n👇 Ism — batafsil karta, 💬 — profiliga o'tib yozish")
    kb = InlineKeyboardBuilder()
    for r in chunk:
        kb.row(
            btn(f"{r.place}. {short_name(r)} — {r.count}" + (f" 🏆{r.wins}" if r.wins else ""), UserCb(action="card", uid=r.user_id)),
            profile_button(r.user, r.user_id, "💬"),
        )
    nav = []
    if page > 0:
        nav.append(btn("◀️", RatingPage(page=page - 1)))
    if page < pages - 1:
        nav.append(btn("▶️", RatingPage(page=page + 1)))
    if nav:
        kb.row(*nav)
    kb.row(btn("⬅️ Menyu", Menu(action="main")))
    await edit(call, "\n".join(lines), kb.as_markup())


# --- Foydalanuvchi kartasi --------------------------------------------------

@router.callback_query(UserCb.filter(F.action == "card"))
async def cb_card(call: CallbackQuery, callback_data: UserCb, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    text, kb = await user_card(session, callback_data.uid)
    await edit(call, text, kb)


@router.callback_query(UserCb.filter(F.action.in_({"win", "unwin"})))
async def cb_win(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    gid = await group_id(session)
    rnd = await repo.current_round(session, gid)
    uid = callback_data.uid
    if callback_data.action == "win":
        st = await repo.user_stats(session, gid, uid)
        n, _ = await repo.add_win(session, rnd.id, uid, st.place, st.round_count)
        note = f"🏆 G'olib deb belgilandi ({n}-marta)"
    else:
        await repo.remove_win(session, rnd.id, uid)
        note = "G'oliblikdan olib tashlandi"
    text, kb = await user_card(session, uid)
    await edit(call, text, kb)
    await call.answer(note, show_alert=False)


@router.callback_query(UserCb.filter(F.action == "members"))
async def cb_members(call: CallbackQuery, callback_data: UserCb, session: AsyncSession) -> None:
    gid = await group_id(session)
    items = await repo.added_members(session, gid, callback_data.uid, limit=40)
    adder = await session.get(repo.User, callback_data.uid)
    lines = [f"👥 {mention(adder, callback_data.uid)} qo'shgan a'zolar (oxirgi 40 ta):", ""]
    for i, (u, a) in enumerate(items, 1):
        status = " <i>(chiqib ketgan)</i>" if a.left_at else ""
        lines.append(f"{i}. {mention(u, a.member_id)} — {repo.fmt_dt(a.added_at)}{status}")
    if not items:
        lines.append("<i>Hech kim yo'q.</i>")
    await edit(call, "\n".join(lines), back_kb(UserCb(action="card", uid=callback_data.uid)))


# --- G'oliblar tarixi -------------------------------------------------------

@router.callback_query(Menu.filter(F.action == "history"))
async def cb_history(call: CallbackQuery, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    lines = ["🏆 <b>G'oliblar tarixi</b> (oxirgi 10 tur)", ""]
    for rnd in await repo.list_rounds(session, gid, limit=10):
        period = f"{repo.fmt_dt(rnd.started_at)} — {repo.fmt_dt(rnd.finished_at) if rnd.finished_at else 'hozir'}"
        lines.append(f"<b>Tur #{rnd.number}</b> ({period})")
        winners = await repo.round_winners(session, rnd.id)
        for w, u in winners[:10]:
            nth = await session.scalar(select(func.count(Win.id)).where(Win.user_id == w.user_id, Win.id <= w.id))
            place = f"{w.place}-o'rin, " if w.place else ""
            lines.append(f"  🏆 {mention(u, w.user_id)} — {place}{w.added_count} ta, <i>{nth}-marta g'olib</i>")
        if not winners:
            lines.append("  <i>g'olib belgilanmagan</i>")
        lines.append("")
    text = "\n".join(lines)
    await edit(call, text[:4000], back_kb())


# --- Yangi tur --------------------------------------------------------------

@router.callback_query(Menu.filter(F.action == "newround"))
async def cb_newround(call: CallbackQuery, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    rnd = await repo.current_round(session, gid)
    kb = InlineKeyboardBuilder()
    kb.row(btn("✅ Ha, yangi tur boshlansin", Menu(action="newround_ok")), btn("❌ Yo'q", Menu(action="main")))
    await edit(
        call,
        f"🔄 <b>Tur #{rnd.number} yakunlansinmi?</b>\n\n"
        "• Reyting noldan boshlanadi.\n"
        "• Eski natijalar va g'oliblar tarixi saqlanib qoladi.\n"
        "• Avval qo'shilgan a'zolar qayta hisoblanmaydi.\n\n"
        "💡 Tur yakunlanishidan oldin g'oliblarga mukofot yuborib qo'yishni unutmang.",
        kb.as_markup(),
    )


@router.callback_query(Menu.filter(F.action == "newround_ok"))
async def cb_newround_ok(call: CallbackQuery, session: AsyncSession) -> None:
    rnd = await repo.start_new_round(session, await group_id(session))
    await call.answer(f"Tur #{rnd.number} boshlandi!", show_alert=True)
    text, kb = await main_menu(session)
    await edit(call, text, kb)


# --- Sozlamalar -------------------------------------------------------------

SETTING_NAMES = {
    "delete_service": "🧹 \"Kim kimni qo'shdi\" xabarlarini o'chirish",
    "subtract_left": "➖ Chiqib ketganlarni hisobdan ayirish",
    "top_enabled": "📢 Guruhda /top buyrug'i",
}


async def settings_view(session: AsyncSession) -> tuple[str, object]:
    gid = await group_id(session)
    kb = InlineKeyboardBuilder()
    for key, name in SETTING_NAMES.items():
        mark = "✅" if await repo.get_flag(session, key) else "❌"
        kb.row(btn(f"{mark} {name}", Menu(action=f"set.{key}")))
    kb.row(btn("⬅️ Menyu", Menu(action="main")))
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"Guruh ID: <code>{gid or 'ulanmagan'}</code>\n"
        "Guruhni almashtirish: yangi guruhda <code>/bind</code> yozing.\n\n"
        "Sozlamani o'zgartirish uchun ustiga bosing."
    )
    return text, kb.as_markup()


@router.callback_query(Menu.filter(F.action == "settings"))
async def cb_settings(call: CallbackQuery, session: AsyncSession) -> None:
    await edit(call, *await settings_view(session))


@router.callback_query(Menu.filter(F.action.startswith("set.")))
async def cb_toggle(call: CallbackQuery, callback_data: Menu, session: AsyncSession) -> None:
    key = callback_data.action.split(".", 1)[1]
    if key in SETTING_NAMES:
        await repo.toggle_flag(session, key)
    await edit(call, *await settings_view(session))


# --- Eksport ----------------------------------------------------------------

@router.callback_query(Menu.filter(F.action == "export"))
async def cb_export(call: CallbackQuery, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    rnd = await repo.current_round(session, gid)
    rows = await repo.rating(session, rnd.id, await repo.get_flag(session, "subtract_left"))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["O'rin", "ID", "Ism", "Username", "Qo'shgan", "G'oliblik soni"])
    for r in rows:
        w.writerow([r.place, r.user_id, full_name(r.user, r.user_id), r.user.username if r.user and r.user.username else "", r.count, r.wins])
    data = buf.getvalue().encode("utf-8-sig")  # Excel o'zbekcha harflarni to'g'ri ko'rsatishi uchun
    await call.message.answer_document(
        BufferedInputFile(data, filename=f"reyting_tur{rnd.number}.csv"),
        caption=f"📥 Tur #{rnd.number} reytingi — {len(rows)} ta qatnashchi",
    )
    await call.answer()
