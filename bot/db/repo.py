"""Ma'lumotlar bazasi bilan ishlash funksiyalari (biznes-mantiq shu yerda)."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Addition, InviteLink, Round, Setting, Template, User, Win, utcnow

# --- Sozlamalar -------------------------------------------------------------

DEFAULTS = {
    "delete_service": "1",  # "X Y ni qo'shdi" kabi xizmat xabarlarini o'chirish
    "subtract_left": "1",  # Guruhdan chiqib ketgan a'zolar hisobdan ayiriladi
    "top_enabled": "1",  # Guruhda /top buyrug'i ishlaydi
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


UNBOUND = "none"  # guruh ataylab uzilgan (egalik topshirilgan) — GROUP_ID (Vercel) ham hisobga olinmaydi


async def get_group_id(s: AsyncSession, fallback: int | None = None) -> int | None:
    value = await get_setting(s, "group_id")
    if value == UNBOUND:
        return None
    return int(value) if value else fallback


# --- Ega va adminlar --------------------------------------------------------
# Ega va adminlar bazada saqlanadi — botni boshqa odamga topshirishda kodga yoki Vercel'ga kirish shart emas.
# ADMIN_IDS (Vercel) ixtiyoriy zaxira "super-admin" bo'lib qoladi.

CLAIM_PREFIX = "own_"


async def get_owner(s: AsyncSession) -> int | None:
    value = await get_setting(s, "owner_id")
    return int(value) if value else None


async def get_admins(s: AsyncSession) -> list[int]:
    value = await get_setting(s, "admin_ids") or ""
    return [int(x) for x in value.split(",") if x]


async def _save_admins(s: AsyncSession, ids: list[int]) -> None:
    await set_setting(s, "admin_ids", ",".join(str(i) for i in dict.fromkeys(ids)))


async def is_owner(s: AsyncSession, user_id: int, env_admins: list[int]) -> bool:
    return user_id in env_admins or user_id == await get_owner(s)


async def is_admin(s: AsyncSession, user_id: int, env_admins: list[int]) -> bool:
    return await is_owner(s, user_id, env_admins) or user_id in await get_admins(s)


async def add_admin(s: AsyncSession, user_id: int) -> None:
    await _save_admins(s, await get_admins(s) + [user_id])


async def remove_admin(s: AsyncSession, user_id: int) -> None:
    await _save_admins(s, [i for i in await get_admins(s) if i != user_id])


async def set_owner(s: AsyncSession, user_id: int) -> None:
    """Yangi ega. Avvalgi ega adminlikdan ham chiqadi; yangi ega yordamchi adminlar ro'yxatida bo'lsa — olib tashlanadi."""
    await set_setting(s, "owner_id", str(user_id))
    await set_setting(s, "owner_claim", "")
    await remove_admin(s, user_id)


async def create_claim_token(s: AsyncSession) -> str:
    """Egalikni topshirish uchun bir martalik kod (eskisi bekor bo'ladi)."""
    import secrets
    token = secrets.token_urlsafe(24)
    await set_setting(s, "owner_claim", token)
    return token


async def try_claim(s: AsyncSession, user_id: int, payload: str | None, setup_secret: str | None) -> str | None:
    """/start <payload> orqali ega bo'lish. "transfer" — bir martalik topshirish kodi, "setup" — ega hali yo'q
    bo'lganda WEBHOOK_SECRET bilan birinchi sozlash. Kod mos kelmasa None."""
    if not payload:
        return None
    import hmac
    token = await get_setting(s, "owner_claim") or ""
    if payload.startswith(CLAIM_PREFIX) and token and hmac.compare_digest(payload[len(CLAIM_PREFIX):], token):
        await set_owner(s, user_id)
        return "transfer"
    if setup_secret and await get_owner(s) is None and hmac.compare_digest(payload, setup_secret):
        await set_owner(s, user_id)
        return "setup"
    return None


async def reset_for_transfer(s: AsyncSession, fallback_group: int | None) -> int | None:
    """Egalik topshirilganda: avvalgi guruh bog'lanishi uziladi va avvalgi yordamchi adminlar o'chiriladi.
    Yangi ega o'z guruhini /bind bilan ulaydi. Avvalgi guruh ID'sini qaytaradi (bot undan chiqishi uchun)."""
    old_group = await get_group_id(s, fallback_group)
    await set_setting(s, "group_id", UNBOUND)
    await set_setting(s, "admin_ids", "")
    for key in ("last_top_msg", "last_top_at"):
        await set_setting(s, key, "")
    return old_group


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

async def record_addition(s: AsyncSession, chat_id: int, adder_id: int, member_id: int, source: str = "add") -> bool:
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
    s.add(Addition(chat_id=chat_id, round_id=rnd.id, adder_id=adder_id, member_id=member_id, source=source))
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
    count: int  # hisob: qo'shganlar (sozlamaga ko'ra chiqib ketganlar ayirilgan)
    wins: int
    added: int = 0  # qo'shganlar (muddatgacha)
    left: int = 0  # shulardan muddatgacha guruhni tark etganlar


async def rating(
    s: AsyncSession, round_id: int, subtract_left: bool, until: datetime | None = None
) -> list[RatingRow]:
    """Tur reytingi. `until` berilsa — faqat shu vaqtgacha qo'shilganlar va shu vaqtgacha chiqib ketganlar hisobga olinadi."""
    left_cond = Addition.left_at.is_not(None)
    if until is not None:
        left_cond = and_(left_cond, Addition.left_at <= until)
    added = func.count(Addition.id).label("added_cnt")
    left = func.coalesce(func.sum(case((left_cond, 1), else_=0)), 0).label("left_cnt")
    score = (added - left) if subtract_left else added
    last = func.max(Addition.added_at).label("last_at")
    q = select(Addition.adder_id, added, left, last).where(Addition.round_id == round_id)
    if until is not None:
        q = q.where(Addition.added_at <= until)
    # Teng natijada — shu songa birinchi yetib kelgan yuqorida turadi. Vaqt bir xil bo'lsa
    # (soat aniqligi yetmasa) — yozuv tartib raqami hal qiladi
    q = (q.group_by(Addition.adder_id).having(score > 0)
         .order_by(score.desc(), last.asc(), func.max(Addition.id).asc()))
    rows = (await s.execute(q)).all()
    if not rows:
        return []
    ids = [r.adder_id for r in rows]
    users = {u.id: u for u in await s.scalars(select(User).where(User.id.in_(ids)))}
    wins = dict(
        (await s.execute(select(Win.user_id, func.count(Win.id)).where(Win.user_id.in_(ids)).group_by(Win.user_id))).all()
    )
    return [
        RatingRow(place=i, user_id=r.adder_id, user=users.get(r.adder_id),
                  count=r.added_cnt - r.left_cnt if subtract_left else r.added_cnt,
                  wins=wins.get(r.adder_id, 0), added=r.added_cnt, left=r.left_cnt)
        for i, r in enumerate(rows, 1)
    ]


async def round_rating(s: AsyncSession, rnd: Round) -> list[RatingRow]:
    """Turning amaldagi reytingi: sozlama va konkurs muddati hisobga olinadi."""
    return await rating(s, rnd.id, await get_flag(s, "subtract_left"), until=rnd.deadline)


# --- Konkurs sharti (muddat va g'olib aniqlash usuli) ------------------------

# O'zbekiston vaqti (UTC+5, yozgi vaqt yo'q). Bazada vaqt UTC'da saqlanadi.
LOCAL_TZ = timezone(timedelta(hours=5))
WIN_MODES = ("top", "goal")


def to_local(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None) if dt else None


def parse_deadline(text: str) -> datetime | None:
    """"05.11.2026" yoki "05.11.2026 18:00" (Toshkent vaqti) -> UTC. Faqat sana bo'lsa — kun oxirigacha."""
    text = " ".join(text.strip().replace("/", ".").replace("-", ".").split())
    for fmt, date_only in (("%d.%m.%Y %H:%M", False), ("%d.%m.%Y", True)):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if date_only:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    return None


async def set_deadline(s: AsyncSession, rnd: Round, deadline: datetime | None) -> None:
    rnd.deadline = deadline
    await s.commit()


async def set_win_rule(s: AsyncSession, rnd: Round, mode: str | None, value: int | None) -> None:
    rnd.win_mode = mode if mode in WIN_MODES else None
    rnd.win_value = value if rnd.win_mode else None
    await s.commit()


def is_finished(rnd: Round) -> bool:
    return rnd.deadline is not None and utcnow() > rnd.deadline


def winners_by_rule(rnd: Round, rows: list[RatingRow]) -> list[RatingRow]:
    """Shart bo'yicha g'oliblar: TOP-N yoki kamida N ta qo'shganlar."""
    if not rnd.win_mode or not rnd.win_value:
        return []
    if rnd.win_mode == "top":
        return rows[: rnd.win_value]
    return [r for r in rows if r.count >= rnd.win_value]


def rule_text(rnd: Round) -> str:
    """Konkurs shartini foydalanuvchilarga tushunarli qilib yozadi (HTML)."""
    parts = []
    if rnd.deadline:
        state = " — <i>yakunlangan</i>" if is_finished(rnd) else ""
        parts.append(f"⏰ Muddat: <b>{fmt_dt(to_local(rnd.deadline))}</b> gacha (Toshkent vaqti){state}")
    if rnd.win_mode == "top" and rnd.win_value:
        parts.append(f"🏆 G'oliblar: eng ko'p odam qo'shgan <b>TOP-{rnd.win_value}</b> ishtirokchi")
    elif rnd.win_mode == "goal" and rnd.win_value:
        parts.append(f"🎯 G'oliblar: kamida <b>{rnd.win_value} ta</b> odam qo'shgan har bir ishtirokchi")
    return "\n".join(parts)


@dataclass
class UserStats:
    user: User | None
    round_count: int
    total_count: int
    left_count: int
    link_count: int
    place: int | None
    wins: int
    won_this_round: bool
    round_added: int = 0  # joriy turda (muddatgacha) qo'shganlari
    round_left: int = 0  # shulardan muddatgacha chiqib ketganlar


async def user_stats(s: AsyncSession, chat_id: int, user_id: int) -> UserStats:
    rnd = await current_round(s, chat_id)
    subtract = await get_flag(s, "subtract_left")
    rows = await round_rating(s, rnd)
    me = next((r for r in rows if r.user_id == user_id), None)
    total_q = select(func.count(Addition.id)).where(Addition.chat_id == chat_id, Addition.adder_id == user_id)
    total = await s.scalar(total_q.where(Addition.left_at.is_(None)) if subtract else total_q) or 0
    left = await s.scalar(total_q.where(Addition.left_at.is_not(None))) or 0
    via_link = await s.scalar(total_q.where(Addition.source == "link")) or 0
    wins = await win_count(s, user_id)
    won = await s.scalar(select(Win.id).where(Win.round_id == rnd.id, Win.user_id == user_id)) is not None
    return UserStats(
        user=await s.get(User, user_id),
        round_count=me.count if me else 0,
        total_count=total,
        left_count=left,
        link_count=via_link,
        place=me.place if me else None,
        wins=wins,
        won_this_round=won,
        round_added=me.added if me else 0,
        round_left=me.left if me else 0,
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


# --- Shaxsiy taklif havolalari ---------------------------------------------

async def get_invite_link(s: AsyncSession, chat_id: int, owner_id: int) -> str | None:
    return await s.scalar(select(InviteLink.link).where(InviteLink.chat_id == chat_id, InviteLink.owner_id == owner_id))


async def save_invite_link(s: AsyncSession, chat_id: int, owner_id: int, link: str) -> None:
    s.add(InviteLink(chat_id=chat_id, owner_id=owner_id, link=link))
    await s.commit()


async def link_owner(s: AsyncSession, chat_id: int, link: str) -> int | None:
    return await s.scalar(select(InviteLink.owner_id).where(InviteLink.chat_id == chat_id, InviteLink.link == link))


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
