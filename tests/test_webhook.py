"""Vercel webhook ilovasi, bazadagi FSM va URL moslash testlari."""
import json
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey

import bot.webhook as webhook
from bot.config import get_settings
from bot.db.fsm_storage import DbStorage
from bot.db.session import normalize_url
from tests.test_flow import FakeSession

SECRET = "test_secret_0123456789"


async def call_app(method: str, path: str, body: bytes = b"", headers: dict | None = None, query: str = ""):
    sent = []
    chunks = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return chunks.pop(0)

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": method, "path": path, "query_string": query.encode(),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    await webhook.app(scope, receive, send)
    return sent[0]["status"], json.loads(sent[1]["body"])


@pytest.fixture
def fake_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/bot.db")
    get_settings.cache_clear()
    fake = FakeSession()
    monkeypatch.setattr(webhook, "create_bot", lambda: Bot("42:TEST", session=fake))
    webhook._dp = webhook._bot = webhook._loop = None
    yield fake
    if webhook._dp is not None:
        for r in webhook._dp.sub_routers[0].sub_routers:
            r._parent_router = None
    webhook._dp = webhook._bot = webhook._loop = None
    get_settings.cache_clear()


def start_update(uid: int, text: str = "/start") -> bytes:
    return json.dumps({
        "update_id": 1,
        "message": {"message_id": 1, "date": int(datetime.now().timestamp()), "text": text,
                    "chat": {"id": uid, "type": "private"},
                    "from": {"id": uid, "is_bot": False, "first_name": "Ali"},
                    "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}]},
    }).encode()


async def test_health(fake_runtime):
    assert await call_app("GET", "/") == (200, {"ok": True, "service": "telegram-konkurs-bot"})


async def test_webhook_rejects_wrong_secret(fake_runtime):
    status, _ = await call_app("POST", "/api/webhook", start_update(5), {"X-Telegram-Bot-Api-Secret-Token": "bad"})
    assert status == 401
    status, _ = await call_app("POST", "/api/webhook", start_update(5))
    assert status == 401
    assert fake_runtime.calls == []


async def test_webhook_processes_update(fake_runtime):
    status, body = await call_app("POST", "/api/webhook", start_update(1),
                                  {"X-Telegram-Bot-Api-Secret-Token": SECRET})
    assert (status, body) == (200, {"ok": True})
    # ADMIN_IDS=1 — admin panel javobi yuborildi
    assert any("AI post" in (getattr(c, "text", "") or "") for c in fake_runtime.calls)


async def test_route_param_from_vercel_rewrite(fake_runtime):
    """Vercel rewrite yo'lni /api/index ga almashtiradi — marshrut ?route= orqali keladi."""
    status, _ = await call_app("POST", "/api/index", start_update(5), query="route=webhook")
    assert status == 401
    status, body = await call_app("GET", "/api/index", query="route=setup&secret=wrong")
    assert (status, body["error"]) == (401, "secret noto'g'ri")


async def test_webhook_survives_bad_json(fake_runtime):
    status, _ = await call_app("POST", "/api/webhook", b"{not json", {"X-Telegram-Bot-Api-Secret-Token": SECRET})
    assert status == 200  # Telegram qayta-qayta yubormasligi uchun


async def test_setup_sets_webhook(fake_runtime):
    assert (await call_app("GET", "/api/setup", query="secret=wrong"))[0] == 401
    from aiogram.methods import GetWebhookInfo, SetWebhook
    from aiogram.types import WebhookInfo

    orig = fake_runtime.make_request

    async def make_request(bot, method, timeout=None):
        if isinstance(method, GetWebhookInfo):
            return WebhookInfo(url="https://my-bot.vercel.app/api/webhook", has_custom_certificate=False,
                               pending_update_count=0, allowed_updates=["chat_member"])
        return await orig(bot, method, timeout)

    fake_runtime.make_request = make_request
    status, body = await call_app("GET", "/api/setup", headers={"Host": "my-bot.vercel.app"}, query=f"secret={SECRET}")
    assert status == 200 and body["ok"] and body["bot"] == "@konkurs_bot"
    sw = [c for c in fake_runtime.calls if isinstance(c, SetWebhook)][0]
    assert sw.url == "https://my-bot.vercel.app/api/webhook" and sw.secret_token == SECRET
    assert "chat_member" in sw.allowed_updates and "my_chat_member" in sw.allowed_updates


async def test_db_fsm_storage(sessionmaker):
    st = DbStorage(sessionmaker)
    key = StorageKey(bot_id=42, chat_id=1, user_id=1)
    assert await st.get_state(key) is None and await st.get_data(key) == {}
    await st.set_state(key, "PrizeStates:custom_text")
    await st.update_data(key, {"selected": [10, 20], "mark_win": True, "matn": "o'zbekcha ✅"})
    assert await st.get_state(key) == "PrizeStates:custom_text"
    assert await st.get_data(key) == {"selected": [10, 20], "mark_win": True, "matn": "o'zbekcha ✅"}
    await st.set_state(key, None)
    assert await st.get_state(key) is None


@pytest.mark.parametrize("url, expected, ssl", [
    ("postgres://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
     "postgresql+asyncpg://u:p@ep-x.neon.tech/db", True),
    ("postgresql://u:p@localhost:5432/db", "postgresql+asyncpg://u:p@localhost:5432/db", False),
    ("sqlite+aiosqlite:///data/bot.db", "sqlite+aiosqlite:///data/bot.db", False),
])
def test_normalize_url(url, expected, ssl):
    out, args = normalize_url(url)
    assert out == expected
    assert (args.get("ssl") == "require") == ssl
