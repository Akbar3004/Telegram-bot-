"""Mukofot yuborish: shablon tanlash -> g'oliblarni belgilash -> yuborish. Hamda qo'lda yozish."""
import asyncio
import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import repo
from ...db.models import Template
from ...utils import PLACEHOLDERS_HELP, mention, render_template
from .common import NO_GROUP, Menu, PrizeCb, TplCb, UserCb, back_kb, btn, edit, group_id, short_name
from .states import PrizeStates, WriteStates

router = Router(name="admin_prize")
SELECT_LIMIT = 30


async def current_rows(session: AsyncSession) -> tuple[int, list[repo.RatingRow]]:
    gid = await group_id(session)
    rnd = await repo.current_round(session, gid)
    return rnd.id, await repo.rating(session, rnd.id, await repo.get_flag(session, "subtract_left"))


# --- 1-qadam: shablon tanlash ----------------------------------------------

async def show_template_choice(call: CallbackQuery, session: AsyncSession) -> None:
    kb = InlineKeyboardBuilder()
    for t in await repo.list_templates(session):
        kb.row(btn(f"📄 {t.title}", PrizeCb(action="tpl", value=t.id)))
    kb.row(btn("✍️ Shu safar uchun matn yozish", PrizeCb(action="custom")))
    kb.row(btn("📝 Shablonlarni boshqarish", TplCb(action="list")), btn("❌ Bekor", Menu(action="main")))
    await edit(call, "🎁 <b>Mukofot yuborish</b>\n\n1️⃣ Qaysi xabar yuborilsin? Shablonni tanlang:", kb.as_markup())


@router.callback_query(PrizeCb.filter(F.action == "start"))
async def cb_start(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await group_id(session) is None:
        return await edit(call, NO_GROUP, back_kb())
    await state.clear()
    await state.update_data(selected=[], mark_win=True, preselected=False)
    await show_template_choice(call, session)


@router.callback_query(UserCb.filter(F.action == "tpl"))
async def cb_user_tpl(call: CallbackQuery, callback_data: UserCb, session: AsyncSession, state: FSMContext) -> None:
    """Foydalanuvchi kartasidan: faqat shu odamga shablon yuborish."""
    await state.clear()
    await state.update_data(selected=[callback_data.uid], mark_win=True, preselected=True)
    await show_template_choice(call, session)


@router.callback_query(PrizeCb.filter(F.action == "tpl"))
async def cb_tpl(call: CallbackQuery, callback_data: PrizeCb, session: AsyncSession, state: FSMContext) -> None:
    await state.update_data(tpl_id=callback_data.value, custom_text=None)
    await after_text_chosen(call, session, state)


@router.callback_query(PrizeCb.filter(F.action == "custom"))
async def cb_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PrizeStates.custom_text)
    await edit(call, "✍️ Yuboriladigan matnni yozing.\n\n" + PLACEHOLDERS_HELP, back_kb(PrizeCb(action="back_tpl")))


@router.callback_query(PrizeCb.filter(F.action == "back_tpl"))
async def cb_back_tpl(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    await show_template_choice(call, session)


@router.message(PrizeStates.custom_text, F.text)
async def got_custom(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(tpl_id=0, custom_text=message.html_text)
    data = await state.get_data()
    text, kb = await (confirm_view if data.get("preselected") else select_view)(session, state)
    await message.answer(text, reply_markup=kb)


async def after_text_chosen(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    view = confirm_view if data.get("preselected") else select_view
    await edit(call, *await view(session, state))


async def get_text(session: AsyncSession, data: dict) -> str | None:
    if data.get("custom_text"):
        return data["custom_text"]
    t = await session.get(Template, data.get("tpl_id") or 0)
    return t.text if t else None


# --- 2-qadam: kimlarga yuborishni belgilash ---------------------------------

async def select_view(session: AsyncSession, state: FSMContext) -> tuple[str, object]:
    data = await state.get_data()
    selected = set(data.get("selected", []))
    _, rows = await current_rows(session)
    kb = InlineKeyboardBuilder()
    for r in rows[:SELECT_LIMIT]:
        mark = "✅" if r.user_id in selected else "▫️"
        wins = f" 🏆{r.wins}" if r.wins else ""
        kb.row(btn(f"{mark} {r.place}. {short_name(r)} — {r.count}{wins}", PrizeCb(action="toggle", value=r.user_id)))
    kb.row(*(btn(f"TOP-{n}", PrizeCb(action="top", value=n)) for n in (1, 3, 5, 10)))
    kb.row(btn("🧹 Tozalash", PrizeCb(action="clear")),
           btn(("✅" if data.get("mark_win", True) else "❌") + " G'olib deb yozish", PrizeCb(action="mark")))
    kb.row(btn(f"➡️ Davom etish ({len(selected)} ta)", PrizeCb(action="next")))
    kb.row(btn("⬅️ Shablon", PrizeCb(action="back_tpl")), btn("❌ Bekor", Menu(action="main")))
    text = (
        "🎁 <b>Mukofot yuborish</b>\n\n2️⃣ Xabar kimlarga yuborilsin? Ro'yxatdan belgilang "
        "yoki TOP tugmalaridan foydalaning.\n\n"
        "<i>«G'olib deb yozish» yoqilgan bo'lsa, tanlanganlar shu turning g'oliblari sifatida "
        "tarixga yoziladi va g'oliblik soni oshadi.</i>"
    )
    if not rows:
        text += "\n\n⚠️ Reyting hozircha bo'sh."
    return text, kb.as_markup()


@router.callback_query(PrizeCb.filter(F.action.in_({"toggle", "top", "clear", "mark"})))
async def cb_select(call: CallbackQuery, callback_data: PrizeCb, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list[int] = list(data.get("selected", []))
    if callback_data.action == "toggle":
        uid = callback_data.value
        if uid in selected:
            selected.remove(uid)
        else:
            selected.append(uid)
    elif callback_data.action == "top":
        _, rows = await current_rows(session)
        selected = [r.user_id for r in rows[: callback_data.value]]
    elif callback_data.action == "clear":
        selected = []
    else:
        await state.update_data(mark_win=not data.get("mark_win", True))
    await state.update_data(selected=selected, preselected=False)
    await edit(call, *await select_view(session, state))


@router.callback_query(PrizeCb.filter(F.action == "back_select"))
async def cb_back_select(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.update_data(preselected=False)
    await edit(call, *await select_view(session, state))


# --- 3-qadam: tasdiqlash ----------------------------------------------------

async def confirm_view(session: AsyncSession, state: FSMContext) -> tuple[str, object]:
    data = await state.get_data()
    selected: list[int] = data.get("selected", [])
    text_tpl = await get_text(session, data)
    round_id, rows = await current_rows(session)
    by_id = {r.user_id: r for r in rows}
    kb = InlineKeyboardBuilder()
    if not selected or text_tpl is None:
        kb.row(btn("⬅️ Orqaga", PrizeCb(action="back_select")))
        return "⚠️ Hech kim tanlanmagan yoki shablon topilmadi.", kb.as_markup()

    mark_win = data.get("mark_win", True)
    mark_txt = "ha" if mark_win else "yo'q"
    lines = ["🎁 <b>Tasdiqlash</b>", "", f"🏆 G'olib deb yoziladi: <b>{mark_txt}</b>", "", "<b>Qabul qiluvchilar:</b>"]
    first_preview = None
    for uid in selected:
        st_user = await session.get(repo.User, uid)
        r = by_id.get(uid)
        wins = await repo.win_count(session, uid)
        already = uid in {w.user_id for w, _ in await repo.round_winners(session, round_id)}
        nth = wins + (1 if mark_win and not already else 0)
        warn = "" if st_user and st_user.started_bot else " ⚠️ <i>botga start bosmagan</i>"
        place = f"{r.place}-o'rin, {r.count} ta" if r else "reytingda yo'q"
        lines.append(f"• {mention(st_user, uid)} — {place}, <b>{nth}-marta</b> g'olib{warn}")
        if first_preview is None:
            first_preview = render_template(text_tpl, user=st_user, user_id=uid, place=r.place if r else None,
                                            count=r.count if r else 0, wins=nth)
    lines += ["", "<b>Xabar ko'rinishi</b> (birinchi qabul qiluvchi uchun):", "———", first_preview, "———"]
    kb.row(btn(f"✅ Yuborish ({len(selected)} ta)", PrizeCb(action="send")))
    kb.row(btn("⬅️ Orqaga", PrizeCb(action="back_select")), btn("❌ Bekor", Menu(action="main")))
    return "\n".join(lines)[:4000], kb.as_markup()


@router.callback_query(PrizeCb.filter(F.action == "next"))
async def cb_next(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not (await state.get_data()).get("selected"):
        return await call.answer("Avval kamida bitta foydalanuvchini belgilang", show_alert=True)
    await edit(call, *await confirm_view(session, state))


# --- 4-qadam: yuborish ------------------------------------------------------

async def safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    for _ in range(3):
        try:
            await bot.send_message(chat_id, text)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except (TelegramForbiddenError, TelegramBadRequest):
            return False
    return False


@router.callback_query(PrizeCb.filter(F.action == "send"))
async def cb_send(call: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list[int] = data.get("selected", [])
    text_tpl = await get_text(session, data)
    if not selected or text_tpl is None:
        return await call.answer("Ma'lumot eskirgan, qaytadan boshlang", show_alert=True)
    await state.clear()
    await call.answer("Yuborilmoqda...")
    await call.message.edit_reply_markup(reply_markup=None)

    round_id, rows = await current_rows(session)
    by_id = {r.user_id: r for r in rows}
    ok, failed = [], []
    for uid in selected:
        user = await session.get(repo.User, uid)
        r = by_id.get(uid)
        if data.get("mark_win", True):
            nth, _ = await repo.add_win(session, round_id, uid, r.place if r else None, r.count if r else 0)
        else:
            nth = await repo.win_count(session, uid)
        text = render_template(text_tpl, user=user, user_id=uid, place=r.place if r else None,
                               count=r.count if r else 0, wins=nth)
        line = f"{mention(user, uid)} — {nth}-marta g'olib"
        if await safe_send(bot, uid, text):
            ok.append(line)
        else:
            if user and user.started_bot:
                await repo.set_started(session, uid, False)
            failed.append(mention(user, uid))
        await asyncio.sleep(0.05)

    report = [f"📬 <b>Natija:</b> {len(ok)} ta yuborildi, {len(failed)} ta yuborilmadi", ""]
    if ok:
        report += ["✅ <b>Yuborildi:</b>"] + [f"• {x}" for x in ok] + [""]
    if failed:
        report += ["❌ <b>Yuborilmadi</b> (botga start bosmagan yoki bloklagan).",
                   "Ismiga bosib, profiliga kirib o'zingiz yozing:"] + [f"• {x}" for x in failed]
    await call.message.answer("\n".join(report)[:4000], reply_markup=back_kb())


# --- Foydalanuvchiga qo'lda yozish (bot orqali) -----------------------------

@router.callback_query(UserCb.filter(F.action == "write"))
async def cb_write(call: CallbackQuery, callback_data: UserCb, session: AsyncSession, state: FSMContext) -> None:
    user = await session.get(repo.User, callback_data.uid)
    await state.set_state(WriteStates.message)
    await state.update_data(target=callback_data.uid)
    warn = "" if user and user.started_bot else "\n\n⚠️ Bu foydalanuvchi botga start bosmagan — xabar yetib bormasligi mumkin."
    await edit(
        call,
        f"✉️ {mention(user, callback_data.uid)} ga yuboriladigan xabarni yozing.\n"
        f"Matn, rasm, video, ovozli xabar — istalgan narsani yuborishingiz mumkin.{warn}",
        back_kb(UserCb(action="card", uid=callback_data.uid)),
    )


@router.message(WriteStates.message)
async def got_write(message: Message, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    uid = (await state.get_data())["target"]
    await state.clear()
    user = await session.get(repo.User, uid)
    try:
        await bot.copy_message(uid, message.chat.id, message.message_id)
        result = f"✅ Xabar {mention(user, uid)} ga yuborildi."
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        result = (f"❌ Yuborilmadi: <code>{html.escape(str(e))}</code>\n"
                  f"Ismiga bosib profiliga o'ting va o'zingiz yozing: {mention(user, uid)}")
    await message.answer(result, reply_markup=back_kb(UserCb(action="card", uid=uid)))
