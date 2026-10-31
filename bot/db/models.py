from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Addition(Base):
    """Kim kimni guruhga qo'shgani. Har bir a'zo guruh bo'yicha faqat bir marta hisoblanadi."""

    __tablename__ = "additions"
    __table_args__ = (UniqueConstraint("chat_id", "member_id", name="uq_addition_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    adder_id: Mapped[int] = mapped_column(BigInteger, index=True)
    member_id: Mapped[int] = mapped_column(BigInteger)
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
