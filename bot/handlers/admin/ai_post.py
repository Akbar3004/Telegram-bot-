"""AI post: kiyim rasmini yuborish -> uslub tanlash -> izoh -> AI rasm -> guruhga joylash."""
from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ... import ai_image
from ...config import get_settings
from .common import AiCb, Menu, btn, edit, group_id
from .states import AiStates

router = Router(name="admin_ai")
CAPTION_LIMIT = 1024  # Telegram rasm izohi chegarasi

NO_KEY = (
    "🎨 <b>AI post hali sozlanmagan.</b>\n\n"
    "Vercel'da <code>GEMINI_API_KEY</code> o'zgaruvchisini qo'shing (Google AI Studio → Get API key), "
    "so'ng Redeploy qiling."
)
SEND_PHOTO = (
    "🎨 <b>AI post</b>\n\n"
    "📷 Kiyim rasmini yuboring.\n\n"
    "💡 Yaxshi natija uchun: yorug' joyda, kiyim butunligicha ko'rinsin, rasm xira bo'lmasin."
)


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[btn("🏠 Bosh menyu", Menu(action="home"))]])


def styles_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, (title, _) in ai_image.STYLES.items():
        kb.button(text=title, callback_data=AiCb(action="style", style=key).pack())
    kb.adjust(2)
    kb.row(btn("❌ Bekor", Menu(action="home")))
    return kb.as_markup()


def result_kb(posted: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not posted:
        kb.row(btn("✅ Guruhga joylash", AiCb(action="post")))
        kb.row(btn("🔄 Qayta yaratish", AiCb(action="again")), btn("🎨 Boshqa uslub", AiCb(action="styles")))
    kb.row(btn("📷 Yangi rasm", Menu(action="ai")), btn("🏠 Bosh menyu", Menu(action="home")))
    return kb.as_markup()


async def start(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    """AI post'ni boshlaydi: rasm kutish holatiga o'tadi."""
    await state.clear()
    if not get_settings().gemini_api_key:
        return NO_KEY, home_kb()
    await state.set_state(AiStates.photo)
    return SEND_PHOTO, home_kb()


@router.callback_query(Menu.filter(F.action == "ai"))
async def cb_ai(call: CallbackQuery, state: FSMContext) -> None:
    await edit(call, *await start(state))


# Rasm: AI post bosqichida yoki admin hech qanday dialogsiz shunchaki rasm yuborsa
@router.message(StateFilter(AiStates.photo, None), F.photo | F.document.mime_type.startswith("image/"))
async def got_photo(message: Message, state: FSMContext) -> None:
    if not get_settings().gemini_api_key:
        await message.answer(NO_KEY, reply_markup=home_kb())
        return
    if message.photo:
        file_id, mime = message.photo[-1].file_id, "image/jpeg"
    else:
        file_id, mime = message.document.file_id, message.document.mime_type
    await state.set_state(None)
    await state.update_data(ai_src=file_id, ai_mime=mime, ai_caption=message.html_text or "", ai_result=None)
    await message.answer("🎨 Qaysi uslubda tayyorlaylik?", reply_markup=styles_kb())


@router.message(AiStates.photo)
async def not_photo(message: Message) -> None:
    await message.answer("📷 Iltimos, kiyim <b>rasmini</b> yuboring.", reply_markup=home_kb())


@router.callback_query(AiCb.filter(F.action == "styles"))
async def cb_styles(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("🎨 Qaysi uslubda tayyorlaylik?", reply_markup=styles_kb())


@router.callback_query(AiCb.filter(F.action == "style"))
async def cb_style(call: CallbackQuery, callback_data: AiCb, bot: Bot, state: FSMContext) -> None:
    if callback_data.style not in ai_image.STYLES:
        return await call.answer()
    data = await state.get_data()
    if not data.get("ai_src"):
        return await call.answer("Avval rasm yuboring", show_alert=True)
    await state.update_data(ai_style=callback_data.style)
    if data.get("ai_caption") or data.get("ai_result"):
        # Izoh avval yozilgan (rasm bilan birga yoki oldingi urinishda) — darhol yaratamiz
        await call.answer()
        return await run_generation(bot, call.from_user.id, state)
    await state.set_state(AiStates.caption)
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn("⏭ Izohsiz", AiCb(action="skip"))]])
    await edit(call, "✍️ Post uchun izoh yozing: nomi, narxi, o'lchamlari...\n\n"
                     "Izoh kerak bo'lmasa — «Izohsiz» tugmasini bosing.", kb)


@router.message(AiStates.caption, F.text)
async def got_caption(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(ai_caption=message.html_text[:CAPTION_LIMIT])
    await run_generation(bot, message.chat.id, state)


@router.callback_query(AiCb.filter(F.action == "skip"))
async def cb_skip(call: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(ai_caption="")
    await call.answer()
    await run_generation(bot, call.from_user.id, state)


@router.callback_query(AiCb.filter(F.action == "again"))
async def cb_again(call: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await call.answer("Qayta yaratilmoqda...")
    await run_generation(bot, call.from_user.id, state)


async def run_generation(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    style = data.get("ai_style")
    if not data.get("ai_src") or style not in ai_image.STYLES:
        await bot.send_message(chat_id, "Ma'lumot eskirgan. Rasmni qaytadan yuboring.", reply_markup=home_kb())
        return
    settings = get_settings()
    progress = await bot.send_message(chat_id, f"⏳ AI rasm tayyorlamoqda ({ai_image.STYLES[style][0]})... "
                                               "Bu 10-40 soniya davom etadi.")
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
    try:
        photo = (await bot.download(data["ai_src"])).read()
        result = await ai_image.generate(settings.gemini_api_key, settings.gemini_image_model, photo, style,
                                         data.get("ai_mime") or "image/jpeg")
    except ai_image.AiImageError as e:
        await bot.edit_message_text(f"❌ {e}", chat_id=chat_id, message_id=progress.message_id, reply_markup=error_kb())
        return
    try:
        await bot.delete_message(chat_id, progress.message_id)
    except TelegramBadRequest:
        pass
    sent = await bot.send_photo(chat_id, BufferedInputFile(result, filename="ai_post.jpg"),
                                caption=data.get("ai_caption") or None, reply_markup=result_kb())
    await state.update_data(ai_result=sent.photo[-1].file_id)


def error_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("🔄 Qayta urinish", AiCb(action="again")), btn("🎨 Boshqa uslub", AiCb(action="styles")))
    kb.row(btn("🏠 Bosh menyu", Menu(action="home")))
    return kb.as_markup()


@router.callback_query(AiCb.filter(F.action == "post"))
async def cb_post(call: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    gid = await group_id(session)
    if gid is None:
        return await call.answer("Guruh ulanmagan: guruhda /bind yozing", show_alert=True)
    # Shu xabardagi rasm — admin eski natija ostidagi tugmani bossa ham aynan o'sha rasm joylanadi
    file_id = call.message.photo[-1].file_id if call.message and call.message.photo else data.get("ai_result")
    if not file_id:
        return await call.answer("Rasm topilmadi, qaytadan yarating", show_alert=True)
    caption = call.message.html_text if call.message and call.message.caption else None
    try:
        await bot.send_photo(gid, file_id, caption=caption)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        return await call.answer(f"Guruhga joylab bo'lmadi: {e}"[:200], show_alert=True)
    await call.answer("✅ Guruhga joylandi", show_alert=True)
    try:
        await call.message.edit_reply_markup(reply_markup=result_kb(posted=True))
    except TelegramBadRequest:
        pass
