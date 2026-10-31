"""Guruh statistikasi: kirish/chiqishlar va a'zolar soni — oyma-oy taqqoslash bilan."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import MemberEvent, MemberSnapshot, utcnow
from .repo import LOCAL_TZ, to_local


def local_today() -> date:
    return to_local(utcnow()).date()


def _upsert(s: AsyncSession, model, values: dict, conflict: list[str], update: dict | None):
    """INSERT ... ON CONFLICT — PostgreSQL va SQLite uchun."""
    if s.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(model).values(**values)
    if update:
        return stmt.on_conflict_do_update(index_elements=conflict, set_=update)
    return stmt.on_conflict_do_nothing(index_elements=conflict)


async def record_event(s: AsyncSession, chat_id: int, user_id: int, kind: str) -> None:
    s.add(MemberEvent(chat_id=chat_id, user_id=user_id, kind=kind))
    await s.commit()


async def has_snapshot_today(s: AsyncSession, chat_id: int) -> bool:
    return await s.get(MemberSnapshot, (chat_id, local_today())) is not None


async def save_snapshot(s: AsyncSession, chat_id: int, count: int) -> None:
    await s.execute(_upsert(s, MemberSnapshot, {"chat_id": chat_id, "day": local_today(), "count": count},
                            ["chat_id", "day"], {"count": count}))
    await s.commit()


def month_start(d: date) -> date:
    return d.replace(day=1)


def prev_month_start(d: date) -> date:
    return (month_start(d) - timedelta(days=1)).replace(day=1)


def _utc(d: date) -> datetime:
    """Toshkent sanasining boshlanishi (00:00) -> UTC (bazadagi vaqtlar UTC'da)."""
    return datetime(d.year, d.month, d.day) - LOCAL_TZ.utcoffset(None)


@dataclass
class Period:
    start: date  # Toshkent sanasi, shu kun ichida
    end: date  # shu kundan oldin (ochiq chegara)
    joins: int = 0
    leaves: int = 0
    members_start: int | None = None  # davr boshidagi a'zolar soni (snapshot bo'lsa)

    @property
    def days(self) -> int:
        return max(1, (min(self.end, local_today() + timedelta(days=1)) - self.start).days)

    @property
    def net(self) -> int:
        return self.joins - self.leaves


async def period_stats(s: AsyncSession, chat_id: int, start: date, end: date) -> Period:
    p = Period(start=start, end=end)
    ev = select(MemberEvent.kind, func.count(MemberEvent.id)).where(
        MemberEvent.chat_id == chat_id, MemberEvent.at >= _utc(start), MemberEvent.at < _utc(end)
    ).group_by(MemberEvent.kind)
    counts = dict((await s.execute(ev)).all())
    p.joins, p.leaves = counts.get("join", 0), counts.get("leave", 0)
    p.members_start = await s.scalar(
        select(MemberSnapshot.count).where(MemberSnapshot.chat_id == chat_id, MemberSnapshot.day >= start,
                                           MemberSnapshot.day < end).order_by(MemberSnapshot.day).limit(1)
    )
    return p


async def tracking_since(s: AsyncSession, chat_id: int) -> date | None:
    """Statistika qaysi kundan beri yig'ilmoqda."""
    first_event = await s.scalar(select(func.min(MemberEvent.at)).where(MemberEvent.chat_id == chat_id))
    first_snap = await s.scalar(select(func.min(MemberSnapshot.day)).where(MemberSnapshot.chat_id == chat_id))
    days = [d for d in (to_local(first_event).date() if first_event else None, first_snap) if d]
    return min(days) if days else None


async def total_leaves(s: AsyncSession, chat_id: int) -> int:
    return await s.scalar(select(func.count(MemberEvent.id)).where(
        MemberEvent.chat_id == chat_id, MemberEvent.kind == "leave")) or 0
