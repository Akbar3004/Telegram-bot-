"""Konkurs sharti (muddat, TOP-N yoki N ta qo'shish), shart bo'yicha g'oliblar va reytingni guruhga yuborish."""
import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ... import board
from ...db import repo
from ..group import result_buttons
from .common import NO_GROUP, Menu, PrizeCb, UserCb, back_kb, btn, edit, group_id, rating_line
from .states import RuleStates

router = Router(name="admin_contest")


# --- Shart ekrani -----------------------------------------------------------

async def rules_view(session: AsyncSession) -> tuple[str, object]:
    gid = await group_id(session)
    if gid is None:
        return NO_GROUP, back_kb()
    rnd = await repo.current_round(session, gid)
    rule = repo.rule_text(rnd) or "<i>Shart belgilanmagan — g'oliblarni o'zingiz tanlaysiz.</i>"
    text = (
        f"🎯 <b>Konkurs sharti</b> (tur #{rnd.number})\n\n{rule}\n\n"
        "<b>Qanday ishlaydi:</b>\n"
        "• <b>Muddat</b> — shu vaqtgacha qo'shilganlar hisoblanadi. Muddatgacha guruhni tark etganlar "
        "hisobdan ayiriladi, muddatdan keyin chiqqanlar esa hisobda qoladi.\n"
        "• <b>TOP-N</b> — muddatgacha eng ko'p odam qo'shgan N nafar g'olib bo'ladi.\n"
        "• <b>N ta qo'shish</b> — kamida N ta odam qo'shgan har bir ishtirokchi g'olib bo'ladi.\n\n"
        "Shart foydalanuvchilarga natijasida va guruhdagi jadvalda ko'rsatiladi."
    )
    kb = InlineKeyboardBuilder()
    kb.row(btn("⏰ Muddat belgilash", Menu(action="rule.deadline")))
    if rnd.deadline:
        kb.row(btn("🗑 Muddatni olib tashlash", Menu(action="rule.nodeadline")))
    kb.row(btn("🏆 TOP-N g'olib", Menu(action="rule.top")), btn("🎯 N ta qo'shganlar g'olib", Menu(action="rule.goal")))
    if rnd.win_mode:
        kb.row(btn("❌ G'olib shartini o'chirish", Menu(action="rule.nomode")))
        kb.row(btn("👑 Shart bo'yicha g'oliblar", Menu(action="winners")))
    kb.row(btn("⬅️ Menyu", Menu(action="main")))
    return text, kb.as_markup()


@router.callback_query(Menu.filter(F.action == "rules"))
async def cb_rules(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await edit(call, *await rules_view(session))


PROMPTS = {
    "rule.deadline": (RuleStates.deadline,
                      "⏰ Konkurs muddatini yozing (Toshkent vaqti):\n\n"
                      "<code>05.11.2026</code> — shu kun oxirigacha (23:59)\n"
                      "<code>05.11.2026 18:00</code> — aniq vaqtgacha"),
    "rule.top": (RuleStates.top, "🏆 Nechta g'olib bo'ladi? Son yozing, masalan: <code>10</code>\n\n"
                                 "Eng ko'p odam qo'shgan shuncha ishtirokchi g'olib deb topiladi."),
    "rule.goal": (RuleStates.goal, "🎯 Kamida nechta odam qo'shgan ishtirokchi g'olib bo'ladi? Son yozing, masalan: <code>100</code>"),
}


@router.callback_query(Menu.filter(F.action.in_(set(PROMPTS))))
async def cb_prompt(call: CallbackQuery, callback_data: Menu, state: FSMContext) -> None:
    st, text = PROMPTS[callback_data.action]
    await state.set_state(st)
    await edit(call, text, back_kb(Menu(action="rules")))


@router.callback_query(Menu.filter(F.action.in_({"rule.nodeadline", "rule.nomode"})))
async def cb_clear(call: CallbackQuery, callback_data: Menu, session: AsyncSession) -> None:
    rnd = await repo.current_round(session, await group_id(session))
    if callback_data.action == "rule.nodeadline":
        await repo.set_deadline(session, rnd, None)
    else:
        await repo.set_win_rule(session, rnd, None, None)
    await edit(call, *await rules_view(session))


async def reply_rules(message: Message, session: AsyncSession, state: FSMContext, note: str) -> None:
    await state.clear()
    text, kb = await rules_view(session)
    await message.answer(f"{note}\n\n{text}", reply_markup=kb)


@router.message(RuleStates.deadline, F.text)
async def got_deadline(message: Message, session: AsyncSession, state: FSMContext) -> None:
    dt = repo.parse_deadline(message.text)
    if dt is None:
        await message.answer("❗️ Sanani tushunmadim. Masalan: <code>05.11.2026</code> yoki <code>05.11.2026 18:00</code>")
        return
    rnd = await repo.current_round(session, await group_id(session))
    await repo.set_deadline(session, rnd, dt)
    note = "✅ Muddat saqlandi."
    if repo.is_finished(rnd):
        note += "\n⚠️ Bu vaqt allaqachon o'tgan — reyting shu vaqtgacha bo'lgan holat bo'yicha hisoblanadi."
    await reply_rules(message, session, state, note)


async def got_number(message: Message, session: AsyncSession, state: FSMContext, mode: str) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❗️ Musbat son yozing, masalan: <code>10</code>")
        return
    rnd = await repo.current_round(session, await group_id(session))
    await repo.set_win_rule(session, rnd, mode, int(text))
    await reply_rules(message, session, state, "✅ G'olib aniqlash sharti saqlandi.")


@router.message(RuleStates.top, F.text)
async def got_top(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await got_number(message, session, state, "top")


@router.message(RuleStates.goal, F.text)
async def got_goal(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await got_number(message, session, state, "goal")


# --- Shart bo'yicha g'oliblar ----------------------------------------------

@router.callback_query(Menu.filter(F.action == "winners"))
async def cb_winners(call: CallbackQuery, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    rnd = await repo.current_round(session, gid)
    winners = repo.winners_by_rule(rnd, await repo.round_rating(session, rnd))
    lines = [f"👑 <b>Shart bo'yicha g'oliblar</b> (tur #{rnd.number})", "", repo.rule_text(rnd) or "", ""]
    if rnd.deadline and not repo.is_finished(rnd):
        lines.append("<i>⏳ Muddat hali tugamagan — ro'yxat o'zgarishi mumkin.</i>\n")
    lines += [rating_line(r) for r in winners[:40]] or ["<i>Hozircha shartni bajargan ishtirokchi yo'q.</i>"]
    if len(winners) > 40:
        lines.append(f"... va yana {len(winners) - 40} nafar")
    kb = InlineKeyboardBuilder()
    for r in winners[:10]:
        kb.row(btn(f"{r.place}. {r.count} ta — kartasi", UserCb(action="card", uid=r.user_id)))
    if winners:
        kb.row(btn(f"🎁 G'oliblarga mukofot yuborish ({len(winners)} ta)", PrizeCb(action="rule_start")))
    kb.row(btn("⬅️ Shart", Menu(action="rules")), btn("🏠 Menyu", Menu(action="main")))
    await edit(call, "\n".join(lines)[:4000], kb.as_markup())


# --- To'liq reytingni guruhga yuborish -------------------------------------

@router.callback_query(Menu.filter(F.action == "post"))
async def cb_post(call: CallbackQuery, session: AsyncSession) -> None:
    gid = await group_id(session)
    if gid is None:
        return await edit(call, NO_GROUP, back_kb())
    rnd = await repo.current_round(session, gid)
    rows = await repo.round_rating(session, rnd)
    kb = InlineKeyboardBuilder()
    kb.row(btn("✅ Ha, guruhga yuborilsin", Menu(action="post_ok")), btn("❌ Yo'q", Menu(action="main")))
    await edit(
        call,
        f"📢 <b>To'liq reyting jadvali guruhga yuborilsinmi?</b>\n\n"
        f"Ishtirokchilar: <b>{len(rows)}</b>\n"
        "Jadvalda har bir ishtirokchining hisobi, qo'shganlari va muddatgacha guruhni tark etganlar soni, "
        "konkurs sharti hamda sonlar qanday hisoblangani tushuntiriladi. Ismlar havolasiz chiqadi.",
        kb.as_markup(),
    )


@router.callback_query(Menu.filter(F.action == "post_ok"))
async def cb_post_ok(call: CallbackQuery, bot: Bot, session: AsyncSession) -> None:
    gid = await group_id(session)
    rnd = await repo.current_round(session, gid)
    rows = await repo.round_rating(session, rnd)
    messages = board.full_board(rnd, rows, await repo.get_flag(session, "subtract_left"))
    kb = await result_buttons(bot)
    sent = 0
    try:
        for i, text in enumerate(messages):
            for _ in range(3):
                try:
                    await bot.send_message(gid, text, reply_markup=kb if i == len(messages) - 1 else None)
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
            sent += 1
        note = f"✅ Jadval guruhga yuborildi ({sent} ta xabar)."
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        note = f"❌ Guruhga yuborib bo'lmadi: {e}. Bot guruhda xabar yoza oladimi?"
    await call.answer(note, show_alert=True)
