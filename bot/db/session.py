import os

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .models import Base


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return create_async_engine(url)


async def init_db(engine: AsyncEngine) -> async_sessionmaker:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)
