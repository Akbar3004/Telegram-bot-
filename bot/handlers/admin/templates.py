"""Mukofot xabarlari shablonlarini boshqarish."""
import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import repo
from ...db.models import Template, User
from ...utils import PLACEHOLDERS_HELP, render_template
from .common import Menu, TplCb, back_kb, btn, edit
from .states import TplStates

router = Router(name="admin_templates")

def preview(text: str, uid: int) -> str:
    """Namuna: o'zgaruvchilar o'rniga misol qiymatlar (havola adminning o'ziga olib boradi)."""
    sample = User(id=uid, first_name="Ali", last_name="Valiyev")
    return render_template(text, user=sample, user_id=uid, place=1, count=25, wins=3)


async def list_view(session: AsyncSession) -> tuple[str, object]:
    tpls = await repo.list_templates(session)
    kb = InlineKeyboardBuilder()
    for t in tpls:
        kb.row(btn(f"📄 {t.title}", TplCb(action="view", tid=t.id)))
    kb.row(btn("➕ Yangi shablon", TplCb(action="new")))
    kb.row(btn("⬅️ Menyu", Menu(action="main")))
    text = "📝 <b>Mukofot xabarlari shablonlari</b>\n\n"
    text += f"Jami: {len(tpls)} ta." if tpls else "Hozircha shablon yo'q. Birinchisini yarating 👇"
    return text, kb.as_markup()


@router.callback_query(TplCb.filter(F.action == "list"))
async def cb_list(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await edit(call, *await list_view(session))


@router.callback_query(TplCb.filter(F.action == "view"))
async def cb_view(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    t = await session.get(Template, callback_data.tid)
    if t is None:
        return await edit(call, *await list_view(session))
    kb = InlineKeyboardBuilder()
    kb.row(btn("✏️ Matnni o'zgartirish", TplCb(action="edit", tid=t.id)), btn("🗑 O'chirish", TplCb(action="del", tid=t.id)))
    kb.row(btn("⬅️ Shablonlar", TplCb(action="list")))
    text = (
        f"📄 <b>{html.escape(t.title)}</b>\n\n<b>Asl matn:</b>\n<code>{html.escape(t.text)}</code>\n\n"
        f"<b>Ko'rinishi (namuna):</b>\n{preview(t.text, call.from_user.id)}"
    )
    await edit(call, text[:4000], kb.as_markup())


@router.callback_query(TplCb.filter(F.action == "del"))
async def cb_del(call: CallbackQuery, callback_data: TplCb) -> None:
    kb = InlineKeyboardBuilder()
    kb.row(btn("✅ Ha, o'chirilsin", TplCb(action="del_ok", tid=callback_data.tid)), btn("❌ Yo'q", TplCb(action="view", tid=callback_data.tid)))
    await edit(call, "🗑 Shablon o'chirilsinmi?", kb.as_markup())


@router.callback_query(TplCb.filter(F.action == "del_ok"))
async def cb_del_ok(call: CallbackQuery, callback_data: TplCb, session: AsyncSession) -> None:
    await repo.delete_template(session, callback_data.tid)
    await edit(call, *await list_view(session))


# --- Yaratish / tahrirlash --------------------------------------------------

@router.callback_query(TplCb.filter(F.action == "new"))
async def cb_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TplStates.title)
    await edit(call, "✏️ Shablon uchun qisqa <b>nom</b> yozing (masalan: <i>1-o'rin mukofoti</i>):", back_kb(TplCb(action="list")))


@router.message(TplStates.title, F.text)
async def got_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(TplStates.text)
    await message.answer("✍️ Endi xabar <b>matnini</b> yuboring.\n\n" + PLACEHOLDERS_HELP, reply_markup=back_kb(TplCb(action="list")))


@router.callback_query(TplCb.filter(F.action == "edit"))
async def cb_edit(call: CallbackQuery, callback_data: TplCb, state: FSMContext) -> None:
    await state.set_state(TplStates.edit_text)
    await state.update_data(tid=callback_data.tid)
    await edit(call, "✍️ Yangi matnni yuboring.\n\n" + PLACEHOLDERS_HELP, back_kb(TplCb(action="view", tid=callback_data.tid)))


async def validate(message: Message, text: str) -> bool:
    """Namuna yuborib ko'ramiz — HTML xato bo'lsa, Telegram rad etadi."""
    try:
        await message.answer("👁 <b>Namuna:</b>\n\n" + preview(text, message.from_user.id))
        return True
    except TelegramBadRequest as e:
        await message.answer(f"❌ Matnda formatlash xatosi bor: <code>{html.escape(str(e))}</code>\nQaytadan yuboring.")
        return False


@router.message(TplStates.text, F.text)
async def got_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = message.html_text  # Telegram formatlashi (qalin, kursiv...) saqlanadi
    if not await validate(message, text):
        return
    data = await state.get_data()
    await repo.add_template(session, data.get("title", "Shablon"), text)
    await state.clear()
    await message.answer("✅ Shablon saqlandi!", reply_markup=(await list_view(session))[1])


@router.message(TplStates.edit_text, F.text)
async def got_edit(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = message.html_text
    if not await validate(message, text):
        return
    data = await state.get_data()
    await repo.update_template(session, data["tid"], text)
    await state.clear()
    await message.answer("✅ Shablon yangilandi!", reply_markup=(await list_view(session))[1])
