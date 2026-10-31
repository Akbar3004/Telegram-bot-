import os

import pytest

os.environ.setdefault("BOT_TOKEN", "42:TEST")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("GROUP_ID", "")

from bot.db.session import init_db, make_engine  # noqa: E402


@pytest.fixture
async def sessionmaker():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    sm = await init_db(engine)
    yield sm
    await engine.dispose()


@pytest.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s
