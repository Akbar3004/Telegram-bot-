"""Handlerlarni haqiqiy Telegram update'lari bilan uchidan-uchigacha tekshirish (soxta Bot sessiyasi)."""
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    CreateChatInviteLink, GetChatMemberCount, GetMe,
    CopyMessage, DeleteMessage, EditMessageText,
    GetChatMember, SendDocument, SendMessage, TelegramMethod,
)
from aiogram.types import (
    CallbackQuery, Chat, ChatInviteLink, ChatMemberAdministrator, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated,
    Message, MessageId, Update, User,
)

from bot.db import repo
from bot.db.fsm_storage import DbStorage
from bot.handlers import setup_routers
from bot.handlers.admin.common import Menu, PrizeCb, RatingPage, UserCb
from bot.middlewares import DbSessionMiddleware

ADMIN = 1
GROUP = Chat(id=-1001, type="supergroup", title="Konkurs")
NOW = datetime.now()


def user(uid: int, name: str = "User") -> User:
    return User(id=uid, is_bot=False, first_name=f"{name}{uid}")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.blocked: set[int] = set()
        self.privacy_restricted: set[int] = set()  # tg://user?id= tugmasini rad etadigan foydalanuvchilar
        self.links = 0
        self.member_count = 120

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, CopyMessage)) and method.chat_id in self.blocked:
            from aiogram.exceptions import TelegramForbiddenError
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        markup = getattr(method, "reply_markup", None)
        if markup is not None and hasattr(markup, "inline_keyboard"):
            for row in markup.inline_keyboard:
                for b in row:
                    if b.url and b.url.startswith("tg://user?id=") and int(b.url.split("=")[1]) in self.privacy_restricted:
                        from aiogram.exceptions import TelegramBadRequest
                        raise TelegramBadRequest(method=method, message="Bad Request: BUTTON_USER_PRIVACY_RESTRICTED")
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="Bot", username="konkurs_bot")
        if isinstance(method, CreateChatInviteLink):
            self.links += 1
            return ChatInviteLink(invite_link=f"https://t.me/+LINK{self.links}", creator=user(42), creates_join_request=False,
                                  is_primary=False, is_revoked=False, name=method.name)
        if isinstance(method, GetChatMember):
            return ChatMemberAdministrator.model_construct(user=user(42), status="administrator", can_delete_messages=True)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=1)
        if isinstance(method, GetChatMemberCount):
            return self.member_count
        if isinstance(method, (SendMessage, SendDocument, EditMessageText)):
            return Message(message_id=1, date=NOW, chat=Chat(id=getattr(method, "chat_id", 0) or 0, type="private"),
                           text=getattr(method, "text", None))
        return True

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):
        yield b""

    def sent(self, cls, chat_id=None):
        return [c for c in self.calls if isinstance(c, cls) and (chat_id is None or c.chat_id == chat_id)]


@pytest.fixture
async def env(sessionmaker):
    from bot.config import get_settings
    get_settings.cache_clear()
    fake = FakeSession()
    bot = Bot("42:TEST", session=fake)
    dp = Dispatcher(storage=DbStorage(sessionmaker))
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    root = setup_routers()
    dp.include_router(root)
    counter = iter(range(1, 10_000))

    async def feed(**kw):
        await dp.feed_update(bot, Update(update_id=next(counter), **kw))

    async def bind():
        await feed(message=Message(message_id=next(counter), date=NOW, chat=GROUP, from_user=user(ADMIN), text="/bind",
                                   entities=[{"type": "bot_command", "offset": 0, "length": 5}]))

    async def add(adder: int, member: int):
        await feed(message=Message(message_id=next(counter), date=NOW, chat=GROUP, from_user=user(adder),
                                   new_chat_members=[user(member)]))
        await feed(chat_member=ChatMemberUpdated(
            chat=GROUP, from_user=user(adder), date=NOW,
            old_chat_member=ChatMemberLeft(user=user(member)), new_chat_member=ChatMemberMember(user=user(member))))

    async def join_link(member: int, link: str):
        await feed(chat_member=ChatMemberUpdated(
            chat=GROUP, from_user=user(member), date=NOW,
            invite_link=ChatInviteLink(invite_link=link, creator=user(42), creates_join_request=False,
                                       is_primary=False, is_revoked=False),
            old_chat_member=ChatMemberLeft(user=user(member)), new_chat_member=ChatMemberMember(user=user(member))))

    async def group_cmd(uid: int, text: str):
        await feed(message=Message(message_id=next(counter), date=NOW, chat=GROUP, from_user=user(uid), text=text,
                                   entities=[{"type": "bot_command", "offset": 0, "length": len(text)}]))

    async def leave(member: int):
        await feed(chat_member=ChatMemberUpdated(
            chat=GROUP, from_user=user(member), date=NOW,
            old_chat_member=ChatMemberMember(user=user(member)), new_chat_member=ChatMemberLeft(user=user(member))))

    async def private(uid: int, text: str):
        await feed(message=Message(message_id=next(counter), date=NOW, chat=Chat(id=uid, type="private"),
                                   from_user=user(uid), text=text,
                                   entities=[{"type": "bot_command", "offset": 0, "length": len(text)}] if text.startswith("/") else None))

    async def click(data, uid: int = ADMIN):
        msg = Message(message_id=999, date=NOW, chat=Chat(id=uid, type="private"), text="x")
        await feed(callback_query=CallbackQuery(id=str(next(counter)), from_user=user(uid), chat_instance="c",
                                                message=msg, data=data if isinstance(data, str) else data.pack()))

    ns = type("Env", (), {})()
    ns.__dict__.update(fake=fake, feed=feed, join_link=join_link, group_cmd=group_cmd, bind=bind, add=add, leave=leave, private=private, click=click, sm=sessionmaker)
    yield ns
    for r in root.sub_routers:  # modul darajasidagi routerlarni keyingi test uchun bo'shatamiz
        r._parent_router = None
    await bot.session.close()


def last_text(fake: FakeSession) -> str:
    for c in reversed(fake.calls):
        if isinstance(c, (SendMessage, EditMessageText)):
            return c.text
    return ""


async def test_full_flow(env):
    fake = env.fake
    await env.bind()
    assert "Guruh ulandi" in last_text(fake)

    await env.add(10, 100)
    await env.add(10, 101)
    await env.add(10, 102)
    await env.add(20, 200)
    await env.add(10, 100)  # takror — hisoblanmaydi
    await env.leave(102)    # chiqib ketdi — ayiriladi

    # "Kim kimni qo'shdi" xizmat xabarlari o'chirildi
    assert len(fake.sent(DeleteMessage)) >= 5

    # Admin /start — reyting darhol ko'rinadi
    await env.private(ADMIN, "/start")
    text = last_text(fake)
    assert "Admin panel" in text and "User10</a> — <b>2</b> ta" in text and "User20</a> — <b>1</b> ta" in text

    # To'liq reyting va foydalanuvchi kartasi
    await env.click(RatingPage(page=0))
    await env.click(UserCb(action="card", uid=10))
    assert "Joriy turda: <b>2</b> ta" in last_text(fake) and "chiqib ketgan: 1" in last_text(fake)

    # Shablon yaratish
    await env.click("t:new:0")
    await env.private(ADMIN, "1-o'rin")
    await env.private(ADMIN, "Tabriklaymiz {name}! {place}-o'rin, {count} ta, {wins}-marta g'olib")
    async with env.sm() as s:
        tpl = (await repo.list_templates(s))[0]

    # Foydalanuvchilar botga start bosadi; 20 esa keyin bloklaydi
    await env.private(10, "/start")
    assert "Hisobingiz: <b>2</b>" in last_text(fake)
    fake.blocked.add(20)

    # Mukofot: shablon -> TOP-3 -> tasdiqlash -> yuborish
    await env.click(PrizeCb(action="start"))
    await env.click(PrizeCb(action="tpl", value=tpl.id))
    await env.click(PrizeCb(action="top", value=3))
    await env.click(PrizeCb(action="next"))
    assert "Tasdiqlash" in last_text(fake)
    await env.click(PrizeCb(action="send"))

    to_winner = fake.sent(SendMessage, chat_id=10)[-1].text
    assert to_winner == "Tabriklaymiz User10! 1-o'rin, 2 ta, 1-marta g'olib"
    report = last_text(fake)
    assert "1 ta yuborildi, 1 ta yuborilmadi" in report and 'tg://user?id=20' in report

    # Yangi tur -> keyingi g'alaba "2-marta" bo'ladi
    await env.click(Menu(action="newround_ok"))
    await env.add(10, 300)
    await env.click(UserCb(action="win", uid=10))
    assert "G'olib bo'lgan: <b>2</b> marta" in last_text(fake)

    # Tarix
    await env.click(Menu(action="history"))
    assert "1-marta g'olib" in last_text(fake) and "2-marta g'olib" in last_text(fake)

    # Qo'lda yozish (copy_message)
    await env.click(UserCb(action="write", uid=10))
    await env.private(ADMIN, "Salom, sovg'angizni olib keting")
    assert fake.sent(CopyMessage, chat_id=10)

    # Eksport
    await env.click(Menu(action="export"))
    assert fake.sent(SendDocument)


async def test_non_admin_cannot_open_panel(env):
    await env.bind()
    await env.private(55, "/start")
    assert "Admin panel" not in last_text(env.fake)
    assert "Sizning natijangiz" in last_text(env.fake)


async def test_other_groups_ignored(env):
    await env.bind()
    other = Chat(id=-2002, type="supergroup", title="Boshqa")
    await env.feed(message=Message(message_id=5, date=NOW, chat=other, from_user=user(10), new_chat_members=[user(11)]))
    async with env.sm() as s:
        rnd = await repo.current_round(s, GROUP.id)
        assert await repo.rating(s, rnd.id, True) == []


async def test_personal_invite_link_counts_for_owner(env):
    await env.bind()
    await env.private(10, "/start link")
    assert "shaxsiy taklif havolangiz" in last_text(env.fake) and "https://t.me/+LINK1" in last_text(env.fake)
    await env.private(10, "/link")  # qayta so'ralsa — o'sha havola, yangisi yaratilmaydi
    assert env.fake.links == 1

    await env.join_link(500, "https://t.me/+LINK1")
    await env.join_link(501, "https://t.me/+LINK1")
    await env.join_link(502, "https://t.me/+OTHER")  # begona havola — hech kimga hisoblanmaydi
    await env.join_link(10, "https://t.me/+LINK1")   # egasining o'zi — hisoblanmaydi
    async with env.sm() as s:
        st = await repo.user_stats(s, GROUP.id, 10)
        assert (st.round_count, st.link_count) == (2, 2)

    await env.private(ADMIN, "/start")
    await env.click(UserCb(action="card", uid=10))
    assert "havola orqali: <b>2</b>" in last_text(env.fake)


async def test_left_members_show_remaining_count(env):
    """25 ta qo'shib, 15 tasi chiqib ketsa — reytingda 10 ta ko'rinadi."""
    await env.bind()
    for m in range(1000, 1025):
        await env.add(10, m)
    for m in range(1000, 1015):
        await env.leave(m)
    async with env.sm() as s:
        st = await repo.user_stats(s, GROUP.id, 10)
        assert (st.round_count, st.left_count) == (10, 15)
    # Sozlama o'chirilsa — 25 ta ko'rinadi
    await env.click(Menu(action="set.subtract_left"))
    async with env.sm() as s:
        assert (await repo.user_stats(s, GROUP.id, 10)).round_count == 25


async def test_top_command_in_group(env):
    await env.bind()
    await env.add(10, 100)
    await env.add(10, 101)
    await env.add(20, 200)
    await env.group_cmd(20, "/top")
    msg = env.fake.sent(SendMessage, chat_id=GROUP.id)[-1]
    assert "TOP-10" in msg.text and "User10 — <b>2</b> ta" in msg.text and "tg://user" not in msg.text
    urls = [row[0].url for row in msg.reply_markup.inline_keyboard]
    assert urls == ["https://t.me/konkurs_bot?start=me", "https://t.me/konkurs_bot?start=link"]
    # Cooldown: darhol qayta /top — yangi xabar chiqmaydi, lekin buyruq o'chiriladi
    before = len(env.fake.sent(SendMessage, chat_id=GROUP.id))
    await env.group_cmd(20, "/top")
    assert len(env.fake.sent(SendMessage, chat_id=GROUP.id)) == before


async def test_user_result_button(env):
    await env.bind()
    await env.add(10, 100)
    await env.add(10, 101)
    await env.leave(101)
    await env.private(10, "/start")
    greeting, stats = env.fake.sent(SendMessage, chat_id=10)[-2:]
    # Pastda doim turadigan "📊 Natijam" tugmasi
    assert greeting.reply_markup.keyboard[0][0].text == "📊 Natijam" and greeting.reply_markup.is_persistent
    assert "Hisobingiz: <b>1</b> ta" in stats.text and "Qo'shganlaringiz: 2 ta, shundan guruhni tark etgan: 1 ta" in stats.text

    before = len(env.fake.sent(SendMessage, chat_id=10))
    await env.private(10, "📊 Natijam")
    assert len(env.fake.sent(SendMessage, chat_id=10)) == before + 1
    assert "Sizning natijangiz" in last_text(env.fake)
    await env.private(10, "🔗 Taklif havolam")
    assert "shaxsiy taklif havolangiz" in last_text(env.fake)


async def test_contest_rules_winners_and_group_board(env):
    await env.bind()
    for m in range(100, 105):
        await env.add(10, m)
    for m in range(200, 203):
        await env.add(20, m)
    await env.add(30, 300)
    await env.leave(104)

    # Muddat va "kamida 3 ta" sharti
    await env.private(ADMIN, "/start")
    await env.click(Menu(action="rules"))
    await env.click(Menu(action="rule.deadline"))
    await env.private(ADMIN, "ertaga")
    assert "tushunmadim" in last_text(env.fake)
    await env.private(ADMIN, "05.11.2099 18:00")
    assert "Muddat saqlandi" in last_text(env.fake) and "05.11.2099 18:00" in last_text(env.fake)
    await env.click(Menu(action="rule.goal"))
    await env.private(ADMIN, "3")
    assert "kamida <b>3 ta</b>" in last_text(env.fake)

    # Foydalanuvchi shartni va qancha qolganini ko'radi
    await env.private(30, "📊 Natijam")
    assert "kamida <b>3 ta</b>" in last_text(env.fake) and "yana <b>2 ta</b> qoldi" in last_text(env.fake)

    await env.click(Menu(action="winners"))
    text = last_text(env.fake)
    assert "User10" in text and "User20" in text and "User30" not in text

    # Shart bo'yicha g'oliblar mukofot oynasida oldindan belgilanadi
    await env.click(PrizeCb(action="start"))
    await env.click(PrizeCb(action="custom"))
    await env.private(ADMIN, "Tabriklaymiz {name}!")
    await env.click(PrizeCb(action="rule"))
    await env.click(PrizeCb(action="next"))
    confirm = last_text(env.fake)
    assert "User10" in confirm and "User20" in confirm and "User30" not in confirm

    # To'liq jadval guruhga: qo'shganlar, chiqib ketganlar va tushuntirish bilan
    before = len(env.fake.sent(SendMessage, chat_id=GROUP.id))
    await env.click(Menu(action="post"))
    assert len(env.fake.sent(SendMessage, chat_id=GROUP.id)) == before  # avval tasdiqlash
    await env.click(Menu(action="post_ok"))
    board = env.fake.sent(SendMessage, chat_id=GROUP.id)[-1]
    assert "To'liq reyting jadvali" in board.text
    assert "User10 — <b>4</b> ta 🏆 <i>(5 qo'shgan, 1 chiqib ketgan)</i>" in board.text
    assert "User30 — <b>1</b> ta" in board.text and "User30 — <b>1</b> ta 🏆" not in board.text
    assert "Muddatgacha chiqib ketganlar: <b>1</b>" in board.text and "Hisob = qo'shgan odamlari" in board.text
    assert "tg://user" not in board.text and board.reply_markup is not None


async def test_profile_buttons_and_privacy_fallback(env):
    await env.bind()
    await env.add(10, 100)
    await env.add(20, 200)
    await env.private(ADMIN, "/start")
    await env.click(UserCb(action="card", uid=10))
    urls = [b.url for row in env.fake.calls[-2].reply_markup.inline_keyboard for b in row if b.url]
    assert "tg://user?id=10" in urls

    # 20 ning maxfiyligi tugmani taqiqlaydi — reyting baribir ochiladi, tugmalarsiz va izoh bilan
    env.fake.privacy_restricted.add(20)
    await env.click(RatingPage(page=0))
    edits = env.fake.sent(EditMessageText)
    assert "maxfiylik" in edits[-1].text
    assert not any((b.url or "").startswith("tg://") for row in edits[-1].reply_markup.inline_keyboard for b in row)


async def test_owner_claim_admins_and_transfer(env):
    from aiogram.methods import AnswerCallbackQuery
    from aiogram.types import SharedUser, UsersShared
    from bot.config import get_settings
    secret = get_settings().webhook_secret
    await env.bind()

    # Ega hali yo'q: begona odam oddiy /start bossa — admin emas
    await env.private(77, "/start")
    assert "Sizning natijangiz" in last_text(env.fake)
    await env.private(77, "/start wrong")
    assert "egasisiz" not in last_text(env.fake)
    # Birinchi sozlash: WEBHOOK_SECRET bilan /start — ega bo'ladi va admin panel ochiladi
    await env.private(77, f"/start {secret}")
    msgs = env.fake.sent(SendMessage, chat_id=77)
    assert "Siz endi botning egasisiz" in msgs[-2].text and "Admin panel" in msgs[-1].text
    # Ega bor — sir bilan boshqa odam ega bo'la olmaydi
    await env.private(55, f"/start {secret}")
    assert "egasisiz" not in last_text(env.fake)

    # Ega admin qo'shadi: ID orqali va kontakt tanlash orqali
    await env.click(Menu(action="admins"), uid=77)
    await env.click(Menu(action="admin_add"), uid=77)
    await env.private(77, "88")
    assert "admin qilindi" in "".join(m.text for m in env.fake.sent(SendMessage, chat_id=77)[-3:])
    await env.click(Menu(action="admin_add"), uid=77)
    await env.feed(message=Message(message_id=5000, date=NOW, chat=Chat(id=77, type="private"), from_user=user(77),
                                   users_shared=UsersShared(request_id=1, users=[SharedUser(user_id=89, first_name="Vali")])))
    async with env.sm() as s:
        assert await repo.get_admins(s) == [88, 89]
    await env.private(88, "/start")
    assert "Admin panel" in last_text(env.fake)
    # Yordamchi admin egalik bo'limiga kira olmaydi
    await env.click(Menu(action="transfer_ok"), uid=88)
    assert env.fake.sent(AnswerCallbackQuery)[-1].show_alert
    async with env.sm() as s:
        assert not await repo.get_setting(s, "owner_claim")

    # Egalikni topshirish: bir martalik havola
    await env.click(Menu(action="transfer_ok"), uid=77)
    link_text = last_text(env.fake)
    token = link_text.split("start=")[1].split("<")[0]
    assert token.startswith("own_")
    await env.private(99, f"/start {token}")
    assert "Admin panel" in env.fake.sent(SendMessage, chat_id=99)[-1].text
    assert "ga o'tdi" in env.fake.sent(SendMessage, chat_id=77)[-1].text
    await env.private(77, "/start")  # eski ega endi oddiy foydalanuvchi
    assert "Sizning natijangiz" in last_text(env.fake)
    await env.private(100, f"/start {token}")  # havola ikkinchi marta ishlamaydi
    assert "Sizning natijangiz" in last_text(env.fake)
    async with env.sm() as s:
        assert await repo.get_owner(s) == 99


async def test_admin_keyboard_and_group_stats(env):
    from datetime import timedelta
    from bot.db import stats
    from bot.db.models import MemberEvent, utcnow

    await env.bind()
    await env.add(10, 100)
    await env.add(10, 101)
    await env.join_link(102, "https://t.me/+NOBODY")  # o'zi kirgan ham statistikaga kiradi
    await env.leave(101)
    # O'tgan oy uchun tarix
    async with env.sm() as s:
        prev = stats._utc(stats.prev_month_start(stats.local_today())) + timedelta(days=2)
        s.add_all([MemberEvent(chat_id=GROUP.id, user_id=500 + i, kind="join", at=prev) for i in range(6)])
        s.add(MemberEvent(chat_id=GROUP.id, user_id=600, kind="leave", at=prev))
        await s.commit()

    await env.private(ADMIN, "/start")
    kb = env.fake.sent(SendMessage, chat_id=ADMIN)[-2].reply_markup
    assert [b.text for b in kb.keyboard[0]] == ["🏆 Konkurs", "📈 Guruh statistikasi"] and kb.is_persistent

    await env.private(ADMIN, "📈 Guruh statistikasi")
    text = last_text(env.fake)
    assert "Hozir a'zolar: <b>120</b>" in text
    assert "Qo'shilganlar: <b>3</b> | 6" in text and "Chiqib ketganlar: <b>1</b> | 1" in text
    assert "Sof o'sish: <b>+2</b> | +5" in text and "ko'rishlar sonini bermaydi" in text

    await env.private(ADMIN, "🏆 Konkurs")
    assert "Admin panel" in last_text(env.fake)
