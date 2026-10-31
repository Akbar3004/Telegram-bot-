"""Ma'lumotlar bazasi bilan ishlash funksiyalari (biznes-mantiq shu yerda)."""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Addition, Round, Setting, Template, User, Win, utcnow

# --- Sozlamalar -------------------------------------------------------------

DEFAULTS = {
    "delete_service": "1",  # "X Y ni qo'shdi" kabi xizmat xabarlarini o'chirish
    "subtract_left": "1",  # Guruhdan chiqib ketgan a'zolar hisobdan ayiriladi
}


async def get_setting(s: AsyncSession, key: str) -> str | None:
    row = await s.get(Setting, key)
    return row.value if row else DEFAULTS.get(key)


async def set_setting(s: AsyncSession, key: str, value: str) -> None:
    row = await s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))
    await s.commit()


async def get_flag(s: AsyncSession, key: str) -> bool:
    return (await get_setting(s, key)) == "1"


async def toggle_flag(s: AsyncSession, key: str) -> bool:
    new = not await get_flag(s, key)
    await set_setting(s, key, "1" if new else "0")
    return new


async def get_group_id(s: AsyncSession, fallback: int | None = None) -> int | None:
    value = await get_setting(s, "group_id")
    return int(value) if value else fallback


# --- Foydalanuvchilar -------------------------------------------------------

async def upsert_user(s: AsyncSession, tg_user, started: bool = False, commit: bool = True) -> User:
    user = await s.get(User, tg_user.id)
    if user is None:
        user = User(id=tg_user.id)
        s.add(user)
    user.first_name = tg_user.first_name or ""
    user.last_name = tg_user.last_name
    user.username = tg_user.username
    if started:
        user.started_bot = True
    if commit:
        await s.commit()
    return user


async def set_started(s: AsyncSession, user_id: int, value: bool) -> None:
    await s.execute(update(User).where(User.id == user_id).values(started_bot=value))
    await s.commit()


# --- Turlar (bosqichlar) ----------------------------------------------------

async def current_round(s: AsyncSession, chat_id: int) -> Round:
    r = await s.scalar(
        select(Round).where(Round.chat_id == chat_id, Round.finished_at.is_(None)).order_by(Round.id.desc())
    )
    if r is None:
        last = await s.scalar(select(func.max(Round.number)).where(Round.chat_id == chat_id)) or 0
        r = Round(chat_id=chat_id, number=last + 1)
        s.add(r)
        await s.commit()
    return r


async def start_new_round(s: AsyncSession, chat_id: int) -> Round:
    old = await current_round(s, chat_id)
    old.finished_at = utcnow()
    await s.commit()
    return await current_round(s, chat_id)


async def list_rounds(s: AsyncSession, chat_id: int, limit: int = 10) -> list[Round]:
    res = await s.scalars(select(Round).where(Round.chat_id == chat_id).order_by(Round.id.desc()).limit(limit))
    return list(res)


# --- Qo'shilganlar ----------------------------------------------------------

async def record_addition(s: AsyncSession, chat_id: int, adder_id: int, member_id: int) -> bool:
    """A'zo qo'shilishini yozadi. Yangi hisoblangan bo'lsa True qaytaradi.

    Bir a'zo guruh bo'yicha faqat BIR marta hisoblanadi (chiqib-qaytib kirish bilan
    hisobni ko'paytirib bo'lmaydi). Qaytib kirgan a'zo asl qo'shgan odamga qaytariladi.
    """
    if adder_id == member_id:
        return False
    existing = await s.scalar(
        select(Addition).where(Addition.chat_id == chat_id, Addition.member_id == member_id)
    )
    if existing:
        if existing.left_at is not None:
            existing.left_at = None
            await s.commit()
        return False
    rnd = await current_round(s, chat_id)
    s.add(Addition(chat_id=chat_id, round_id=rnd.id, adder_id=adder_id, member_id=member_id))
    try:
        await s.commit()
    except Exception:  # bir vaqtda kelgan ikki update (unique cheklov)
        await s.rollback()
        return False
    return True


async def mark_rejoined(s: AsyncSession, chat_id: int, member_id: int) -> None:
    await s.execute(
        update(Addition)
        .where(Addition.chat_id == chat_id, Addition.member_id == member_id)
        .values(left_at=None)
    )
    await s.commit()


async def mark_left(s: AsyncSession, chat_id: int, member_id: int) -> None:
    await s.execute(
        update(Addition)
        .where(Addition.chat_id == chat_id, Addition.member_id == member_id, Addition.left_at.is_(None))
        .values(left_at=utcnow())
    )
    await s.commit()


# --- Reyting ----------------------------------------------------------------

@dataclass
class RatingRow:
    place: int
    user_id: int
    user: User | None
    count: int
    wins: int


async def rating(s: AsyncSession, round_id: int, subtract_left: bool) -> list[RatingRow]:
    cnt = func.count(Addition.id).label("cnt")
    last = func.max(Addition.added_at).label("last")
    q = select(Addition.adder_id, cnt, last).where(Addition.round_id == round_id)
    if subtract_left:
        q = q.where(Addition.left_at.is_(None))
    # Teng natijada — shu songa birinchi yetib kelgan yuqorida turadi
    q = q.group_by(Addition.adder_id).order_by(cnt.desc(), last.asc())
    rows = (await s.execute(q)).all()
    if not rows:
        return []
    ids = [r.adder_id for r in rows]
    users = {u.id: u for u in await s.scalars(select(User).where(User.id.in_(ids)))}
    wins = dict(
        (await s.execute(select(Win.user_id, func.count(Win.id)).where(Win.user_id.in_(ids)).group_by(Win.user_id))).all()
    )
    return [
        RatingRow(place=i, user_id=r.adder_id, user=users.get(r.adder_id), count=r.cnt, wins=wins.get(r.adder_id, 0))
        for i, r in enumerate(rows, 1)
    ]


@dataclass
class UserStats:
    user: User | None
    round_count: int
    total_count: int
    left_count: int
    place: int | None
    wins: int
    won_this_round: bool


async def user_stats(s: AsyncSession, chat_id: int, user_id: int) -> UserStats:
    rnd = await current_round(s, chat_id)
    subtract = await get_flag(s, "subtract_left")
    rows = await rating(s, rnd.id, subtract)
    me = next((r for r in rows if r.user_id == user_id), None)
    total_q = select(func.count(Addition.id)).where(Addition.chat_id == chat_id, Addition.adder_id == user_id)
    total = await s.scalar(total_q.where(Addition.left_at.is_(None)) if subtract else total_q) or 0
    left = await s.scalar(total_q.where(Addition.left_at.is_not(None))) or 0
    wins = await win_count(s, user_id)
    won = await s.scalar(select(Win.id).where(Win.round_id == rnd.id, Win.user_id == user_id)) is not None
    return UserStats(
        user=await s.get(User, user_id),
        round_count=me.count if me else 0,
        total_count=total,
        left_count=left,
        place=me.place if me else None,
        wins=wins,
        won_this_round=won,
    )


async def added_members(s: AsyncSession, chat_id: int, adder_id: int, limit: int = 30) -> list[tuple[User | None, Addition]]:
    adds = list(
        await s.scalars(
            select(Addition)
            .where(Addition.chat_id == chat_id, Addition.adder_id == adder_id)
            .order_by(Addition.id.desc())
            .limit(limit)
        )
    )
    users = {u.id: u for u in await s.scalars(select(User).where(User.id.in_([a.member_id for a in adds])))}
    return [(users.get(a.member_id), a) for a in adds]


# --- G'oliblar --------------------------------------------------------------

async def win_count(s: AsyncSession, user_id: int) -> int:
    return await s.scalar(select(func.count(Win.id)).where(Win.user_id == user_id)) or 0


async def add_win(s: AsyncSession, round_id: int, user_id: int, place: int | None, count: int) -> tuple[int, bool]:
    """G'olibni yozadi. (nechanchi_marta, yangi_yozildimi) qaytaradi."""
    exists = await s.scalar(select(Win).where(Win.round_id == round_id, Win.user_id == user_id))
    if exists is None:
        s.add(Win(round_id=round_id, user_id=user_id, place=place, added_count=count))
        await s.commit()
    return await win_count(s, user_id), exists is None


async def remove_win(s: AsyncSession, round_id: int, user_id: int) -> None:
    await s.execute(delete(Win).where(Win.round_id == round_id, Win.user_id == user_id))
    await s.commit()


async def round_winners(s: AsyncSession, round_id: int) -> list[tuple[Win, User | None]]:
    wins = list(await s.scalars(select(Win).where(Win.round_id == round_id).order_by(Win.place, Win.id)))
    users = {u.id: u for u in await s.scalars(select(User).where(User.id.in_([w.user_id for w in wins])))}
    return [(w, users.get(w.user_id)) for w in wins]


# --- Shablonlar -------------------------------------------------------------

async def list_templates(s: AsyncSession) -> list[Template]:
    return list(await s.scalars(select(Template).order_by(Template.id)))


async def add_template(s: AsyncSession, title: str, text: str) -> Template:
    t = Template(title=title[:100], text=text)
    s.add(t)
    await s.commit()
    return t


async def update_template(s: AsyncSession, template_id: int, text: str) -> None:
    await s.execute(update(Template).where(Template.id == template_id).values(text=text))
    await s.commit()


async def delete_template(s: AsyncSession, template_id: int) -> None:
    await s.execute(delete(Template).where(Template.id == template_id))
    await s.commit()


def fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
