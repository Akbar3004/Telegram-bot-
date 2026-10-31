from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Bot ko'rgan har bir Telegram foydalanuvchisi."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Botga /start bosganmi — bot faqat shunday foydalanuvchilarga xabar yubora oladi
    started_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Round(Base):
    """Konkurs bosqichi (tur). Reyting har bir tur uchun alohida hisoblanadi."""

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # G'olib aniqlash sharti. deadline (UTC) — shu vaqtgacha qo'shilganlar hisoblanadi.
    # win_mode: "top" — eng ko'p qo'shgan win_value nafar; "goal" — kamida win_value ta qo'shganlar.
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    win_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    win_value: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Addition(Base):
    """Kim kimni guruhga qo'shgani. Har bir a'zo guruh bo'yicha faqat bir marta hisoblanadi."""

    __tablename__ = "additions"
    __table_args__ = (UniqueConstraint("chat_id", "member_id", name="uq_addition_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    adder_id: Mapped[int] = mapped_column(BigInteger, index=True)
    member_id: Mapped[int] = mapped_column(BigInteger)
    # "add" — o'zi qo'shgan, "link" — shaxsiy taklif havolasi orqali kirgan
    source: Mapped[str] = mapped_column(String(8), default="add", server_default="add")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Win(Base):
    """G'oliblar tarixi — foydalanuvchi nechanchi marta g'olib bo'lganini shu yerdan bilamiz."""

    __tablename__ = "wins"
    __table_args__ = (UniqueConstraint("round_id", "user_id", name="uq_win_round_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Template(Base):
    """Oldindan yozib qo'yilgan mukofot xabarlari."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class InviteLink(Base):
    """Ishtirokchining shaxsiy taklif havolasi: shu havola orqali kirganlar unga hisoblanadi."""

    __tablename__ = "invite_links"
    __table_args__ = (UniqueConstraint("chat_id", "owner_id", name="uq_link_owner"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    link: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MemberEvent(Base):
    """Guruhga kirish/chiqish tarixi (statistika uchun): har bir a'zo, kim qo'shganidan qat'i nazar."""

    __tablename__ = "member_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(8))  # "join" yoki "leave"
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MemberSnapshot(Base):
    """Guruh a'zolari soni — kuniga bir marta yoziladi (oyma-oy taqqoslash uchun)."""

    __tablename__ = "member_snapshots"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class FsmRecord(Base):
    """Admin panel dialog holati (FSM). Serverless'da xotira saqlanmagani uchun bazada turadi."""

    __tablename__ = "fsm_states"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
