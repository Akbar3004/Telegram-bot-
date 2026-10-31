import os

import pytest

os.environ.setdefault("BOT_TOKEN", "42:TEST")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("GROUP_ID", "")
os.environ.setdefault("WEBHOOK_SECRET", "test_secret_0123456789")

from bot.db.models import Base  # noqa: E402
from bot.db.session import init_db, make_engine  # noqa: E402

# PostgreSQL'da ham sinash uchun: TEST_POSTGRES_URL=postgresql://user@host:port/db pytest
DB_URLS = ["sqlite+aiosqlite:///:memory:"]
if os.getenv("TEST_POSTGRES_URL"):
    DB_URLS.append(os.environ["TEST_POSTGRES_URL"])


@pytest.fixture(params=DB_URLS, ids=lambda u: u.split(":")[0])
async def sessionmaker(request):
    engine = make_engine(request.param)
    if not request.param.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    sm = await init_db(engine)
    yield sm
    await engine.dispose()


@pytest.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s
