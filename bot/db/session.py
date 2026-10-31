import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .models import Base

# Joriy sessionmaker. Serverless (Vercel) muhitida har bir event loop uchun qayta yaratiladi,
# shuning uchun middleware va FSM storage uni shu yerdan oladi.
_sessionmaker: async_sessionmaker | None = None


def set_sessionmaker(sm: async_sessionmaker) -> None:
    global _sessionmaker
    _sessionmaker = sm


def get_sessionmaker() -> async_sessionmaker:
    if _sessionmaker is None:
        raise RuntimeError("Ma'lumotlar bazasi hali ishga tushirilmagan")
    return _sessionmaker


def is_serverless() -> bool:
    return bool(os.getenv("VERCEL") or os.getenv("SERVERLESS"))


def normalize_url(url: str) -> tuple[str, dict]:
    """Neon/Vercel/Supabase bergan `postgres://...?sslmode=require` havolasini asyncpg uchun moslaydi."""
    connect_args: dict = {}
    if url.startswith(("postgres://", "postgresql://")):
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)  # asyncpg bu parametrni tushunmaydi
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = "require"
        # PgBouncer (Neon "pooled" havolasi) bilan prepared statement'lar muammo qilmasligi uchun
        connect_args["statement_cache_size"] = 0
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url, connect_args


def make_engine(url: str) -> AsyncEngine:
    url, connect_args = normalize_url(url)
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    kwargs: dict = {"connect_args": connect_args}
    if url.startswith("postgresql") and is_serverless():
        kwargs["poolclass"] = NullPool  # serverless'da ochiq ulanishlarni ushlab turmaymiz
    elif url.startswith("postgresql"):
        kwargs["pool_pre_ping"] = True
    if url.startswith("postgresql"):
        connect_args.setdefault("server_settings", {"application_name": "telegram-konkurs-bot"})
    return create_async_engine(url, **kwargs)


async def init_db(engine: AsyncEngine) -> async_sessionmaker:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    set_sessionmaker(sm)
    return sm


def _add_missing_columns(conn) -> None:
    """Oddiy migratsiya: eski bazada yangi ustunlar bo'lmasa, qo'shib qo'yadi (ma'lumotlar saqlanadi)."""
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            if col.server_default is not None:
                ddl += f" DEFAULT '{col.server_default.arg}'"
            conn.execute(text(ddl))
