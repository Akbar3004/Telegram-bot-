"""Ega va adminlar: admin qo'shish/olib tashlash va egalikni bir martalik havola bilan topshirish."""
import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, KeyboardButton, KeyboardButtonRequestUsers, Message, MessageOriginUser, ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ...commands import reset_commands, set_admin_commands
from ...config import get_settings
from ...db import repo
from ...utils import mention
from .common import ADMIN_KB, Menu, UserCb, btn, edit, main_menu
from .states import AdminStates

router = Router(name="admin_owner")
PICK_REQUEST_ID = 1
BTN_CANCEL = "❌ Bekor qilish"
PICK_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Kontaktlardan tanlash",
                        request_users=KeyboardButtonRequestUsers(request_id=PICK_REQUEST_ID, user_is_bot=False,
                                                                 max_quantity=1))],
        [KeyboardButton(text=BTN_CANCEL)],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


async def is_owner(session: AsyncSession, uid: int) -> bool:
    return await repo.is_owner(session, uid, get_settings().admin_ids)


# --- Egalikni olish (/start <kod>) — admin va oddiy foydalanuvchi /start'idan chaqiriladi ----------

async def claim_and_greet(message: Message, bot: Bot, session: AsyncSession, payload: str | None) -> bool:
    old_owner = await repo.get_owner(session)
    if not await repo.try_claim(session, message.from_user.id, payload, get_settings().webhook_secret):
        return False
    uid = message.from_user.id
    await repo.upsert_user(session, message.from_user, started=True)
    await set_admin_commands(bot, uid)
    await message.answer("👑 <b>Siz endi botning egasisiz!</b>\n\n"
                         "Konkursni boshqarish, adminlar qo'shish va guruh statistikasini ko'rish sizga ochiq.",
                         reply_markup=ADMIN_KB)
    text, kb = await main_menu(session)
    await message.answer(text, reply_markup=kb)
    if old_owner and old_owner != uid:
        await reset_commands(bot, old_owner)
        try:
            await bot.send_message(old_owner, f"🔁 Bot egaligi {mention(await session.get(repo.User, uid), uid)} ga "
                                              "o'tdi. Siz endi admin emassiz.")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
    return True


# --- Adminlar ro'yxati ------------------------------------------------------

async def admins_view(session: AsyncSession) -> tuple[str, object]:
    owner = await repo.get_owner(session)
    admins = await repo.get_admins(session)
    env = get_settings().admin_ids
    lines = ["👥 <b>Adminlar va egalik</b>", ""]
    lines.append(f"👑 Ega: {mention(await session.get(repo.User, owner), owner)}" if owner else "👑 Ega: <i>belgilanmagan</i>")
    lines.append("")
    lines.append("<b>Yordamchi adminlar</b> (konkursni boshqaradi, admin qo'sha olmaydi):")
    kb = InlineKeyboardBuilder()
    for uid in admins:
        lines.append(f"• {mention(await session.get(repo.User, uid), uid)}")
        kb.row(btn(f"❌ Olib tashlash: {uid}", UserCb(action="unadmin", uid=uid)))
    if not admins:
        lines.append("<i>yo'q</i>")
    if env:
        lines += ["", "<i>ℹ️ Vercel'dagi ADMIN_IDS ham har doim ega huquqiga ega: "
                  + ", ".join(f"<code>{i}</code>" for i in env)
                  + ". Botni sotsangiz, bu o'zgaruvchini Vercel'dan olib tashlang.</i>"]
    kb.row(btn("➕ Admin qo'shish", Menu(action="admin_add")))
    kb.row(btn("🔁 Egalikni topshirish", Menu(action="transfer")))
    kb.row(btn("⬅️ Menyu", Menu(action="main")))
    return "\n".join(lines), kb.as_markup()


async def owner_only(call: CallbackQuery, session: AsyncSession) -> bool:
    if await is_owner(session, call.from_user.id):
        return True
    await call.answer("Bu bo'lim faqat bot egasi uchun", show_alert=True)
    return False


@router.callback_query(Menu.filter(F.action == "admins"))
async def cb_admins(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await owner_only(call, session):
        await state.clear()
        await edit(call, *await admins_view(session))


@router.callback_query(UserCb.filter(F.action == "unadmin"))
async def cb_unadmin(call: CallbackQuery, callback_data: UserCb, bot: Bot, session: AsyncSession) -> None:
    if await owner_only(call, session):
        await repo.remove_admin(session, callback_data.uid)
        await reset_commands(bot, callback_data.uid)
        await edit(call, *await admins_view(session))


# --- Admin qo'shish ---------------------------------------------------------

@router.callback_query(Menu.filter(F.action == "admin_add"))
async def cb_admin_add(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await owner_only(call, session):
        return
    await state.set_state(AdminStates.add)
    await call.answer()
    await call.message.answer(
        "➕ <b>Yangi admin</b>\n\n"
        "Pastdagi «👤 Kontaktlardan tanlash» tugmasini bosing, yoki o'sha odamning istalgan xabarini shu yerga "
        "forward qiling, yoki uning Telegram ID raqamini yozing.\n\n"
        "<i>Admin botga /start bosgan bo'lishi kerak — aks holda bot unga panelni ko'rsata olmaydi.</i>",
        reply_markup=PICK_KB,
    )


async def finish_add(message: Message, bot: Bot, session: AsyncSession, state: FSMContext, uid: int) -> None:
    await state.clear()
    if await is_owner(session, uid):
        await message.answer("Bu odam allaqachon ega.", reply_markup=ADMIN_KB)
    else:
        await repo.add_admin(session, uid)
        await set_admin_commands(bot, uid)
        user = await session.get(repo.User, uid)
        await message.answer(f"✅ {mention(user, uid)} admin qilindi.", reply_markup=ADMIN_KB)
        try:
            await bot.send_message(uid, "👋 Siz konkurs botida admin qilib tayinlandingiz. /start bosing.")
        except (TelegramBadRequest, TelegramForbiddenError):
            await message.answer("⚠️ Unga xabar yuborib bo'lmadi — botga /start bosishini so'rang.")
    text, kb = await admins_view(session)
    await message.answer(text, reply_markup=kb)


@router.message(AdminStates.add, F.users_shared)
async def got_shared(message: Message, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    shared = message.users_shared.users[0]
    if shared.first_name:
        # Kontaktdan tanlanganda ism ham keladi — reytingda chiroyli ko'rinsin
        from types import SimpleNamespace
        await repo.upsert_user(session, SimpleNamespace(id=shared.user_id, first_name=shared.first_name,
                                                        last_name=shared.last_name, username=shared.username))
    await finish_add(message, bot, session, state, shared.user_id)


@router.message(AdminStates.add, F.text == BTN_CANCEL)
async def add_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=ADMIN_KB)


@router.message(AdminStates.add)
async def got_admin(message: Message, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    origin = message.forward_origin
    if isinstance(origin, MessageOriginUser):
        await repo.upsert_user(session, origin.sender_user)
        return await finish_add(message, bot, session, state, origin.sender_user.id)
    text = (message.text or "").strip()
    if text.isdigit():
        return await finish_add(message, bot, session, state, int(text))
    if origin is not None:
        await message.answer("⚠️ Bu odamning maxfiylik sozlamasi forward orqali ID'ni yashiradi. "
                             "«👤 Kontaktlardan tanlash» tugmasidan foydalaning yoki ID raqamini yozing.")
    else:
        await message.answer("Kontaktni tanlang, xabarini forward qiling yoki ID raqamini yozing.")


# --- Egalikni topshirish ----------------------------------------------------

@router.callback_query(Menu.filter(F.action == "transfer"))
async def cb_transfer(call: CallbackQuery, session: AsyncSession) -> None:
    if not await owner_only(call, session):
        return
    kb = InlineKeyboardBuilder()
    kb.row(btn("✅ Ha, havola yaratilsin", Menu(action="transfer_ok")), btn("❌ Yo'q", Menu(action="admins")))
    await edit(call,
               "🔁 <b>Egalikni topshirish</b>\n\n"
               "Bot bir martalik maxfiy havola yaratadi. Uni yangi egaga yuborasiz — u havolani bosib "
               "botga /start bosgan zahoti <b>ega bo'ladi</b>, siz esa adminlikdan chiqasiz.\n\n"
               "• Havola faqat bir marta ishlaydi.\n"
               "• Yangi havola yaratilsa yoki bekor qilinsa, eskisi ishlamaydi.\n"
               "• Konkurs ma'lumotlari, reyting va tarix saqlanib qoladi.",
               kb.as_markup())


@router.callback_query(Menu.filter(F.action == "transfer_ok"))
async def cb_transfer_ok(call: CallbackQuery, bot: Bot, session: AsyncSession) -> None:
    if not await owner_only(call, session):
        return
    token = await repo.create_claim_token(session)
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={repo.CLAIM_PREFIX}{token}"
    kb = InlineKeyboardBuilder()
    kb.row(btn("🚫 Havolani bekor qilish", Menu(action="transfer_cancel")))
    kb.row(btn("⬅️ Adminlar", Menu(action="admins")))
    await edit(call,
               "🔗 <b>Egalikni topshirish havolasi:</b>\n\n"
               f"<code>{html.escape(link)}</code>\n\n"
               "Havolani yangi egaga yuboring. ⚠️ Uni boshqa hech kimga bermang — kim birinchi bossa, o'sha ega bo'ladi.",
               kb.as_markup())


@router.callback_query(Menu.filter(F.action == "transfer_cancel"))
async def cb_transfer_cancel(call: CallbackQuery, session: AsyncSession) -> None:
    if await owner_only(call, session):
        await repo.set_setting(session, "owner_claim", "")
        text, kb = await admins_view(session)
        await edit(call, "🚫 Topshirish havolasi bekor qilindi.\n\n" + text, kb)
