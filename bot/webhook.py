"""Vercel (serverless) uchun webhook ilova — tashqi kutubxonasiz, sof ASGI.

Yo'llar:
  POST .../webhook          — Telegram yangilanishlari (X-Telegram-Bot-Api-Secret-Token tekshiriladi)
  GET  .../setup?secret=..  — webhookni o'rnatish va bot buyruqlarini sozlash (bir marta ochiladi)
  GET  boshqa               — holat tekshiruvi
"""
import asyncio
import hmac
import json
import logging
from urllib.parse import parse_qs

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from .app import create_bot, create_dispatcher, setup_bot_commands
from .config import get_settings
from .db.session import init_db, make_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot.webhook")

_dp: Dispatcher | None = None
_bot: Bot | None = None
_loop: asyncio.AbstractEventLoop | None = None


async def runtime() -> tuple[Bot, Dispatcher]:
    """Bot, baza va dispatcher'ni tayyorlaydi. Event loop almashsa (serverless), loop'ga bog'liqlarini qayta yaratadi."""
    global _dp, _bot, _loop
    if _dp is None:
        _dp = create_dispatcher()
    loop = asyncio.get_running_loop()
    if _loop is not loop:
        await init_db(make_engine(get_settings().database_url))
        _bot = create_bot()
        _loop = loop
    return _bot, _dp


def secrets_equal(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


async def read_body(receive) -> bytes:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            return body


async def respond(send, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8")]})
    await send({"type": "http.response.body", "body": data})


async def handle_webhook(headers: dict, body: bytes) -> tuple[int, dict]:
    if not secrets_equal(headers.get("x-telegram-bot-api-secret-token"), get_settings().webhook_secret):
        return 401, {"ok": False, "error": "unauthorized"}
    bot, dp = await runtime()
    try:
        update = Update.model_validate(json.loads(body), context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:
        # Telegram'ga baribir 200 qaytaramiz — aks holda u shu update'ni qayta-qayta yuboraveradi
        log.exception("Update'ni qayta ishlashda xato")
    return 200, {"ok": True}


async def handle_setup(headers: dict, query: dict) -> tuple[int, dict]:
    settings = get_settings()
    if not settings.webhook_secret:
        return 500, {"ok": False, "error": "WEBHOOK_SECRET o'rnatilmagan"}
    if not secrets_equal((query.get("secret") or [None])[0], settings.webhook_secret):
        return 401, {"ok": False, "error": "secret noto'g'ri"}
    host = headers.get("x-forwarded-host") or headers.get("host")
    url = f"https://{host}/api/webhook"
    bot, dp = await runtime()
    await bot.set_webhook(
        url,
        secret_token=settings.webhook_secret,
        allowed_updates=dp.resolve_used_update_types(),  # chat_member ham kiradi
        drop_pending_updates=False,
    )
    await setup_bot_commands(bot)
    info = await bot.get_webhook_info()
    me = await bot.me()
    return 200, {"ok": True, "bot": f"@{me.username}", "webhook": info.url,
                 "allowed_updates": info.allowed_updates, "pending_updates": info.pending_update_count}


async def app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    path = scope.get("path", "").rstrip("/")
    method = scope.get("method", "GET")
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    query = parse_qs(scope.get("query_string", b"").decode())
    # Vercel rewrite (vercel.json) yo'lni /api/index ga almashtiradi, shuning uchun marshrut ?route= orqali keladi
    route = (query.get("route") or [""])[0]
    try:
        if (route == "webhook" or path.endswith("/webhook")) and method == "POST":
            status, payload = await handle_webhook(headers, await read_body(receive))
        elif route == "setup" or path.endswith("/setup"):
            status, payload = await handle_setup(headers, query)
        else:
            status, payload = 200, {"ok": True, "service": "telegram-konkurs-bot"}
    except Exception as e:
        log.exception("So'rovda xato")
        status, payload = 500, {"ok": False, "error": type(e).__name__}
    await respond(send, status, payload)
