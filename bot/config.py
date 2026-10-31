from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_ids: Annotated[list[int], NoDecode] = []
    group_id: int | None = None
    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    # Webhook (Vercel) rejimi uchun maxfiy kalit: Telegram so'rovlarini tekshirish va /api/setup ni himoyalash
    webhook_secret: str | None = None
    # AI post: Google AI Studio'dan olingan Gemini API kaliti va rasm modeli
    gemini_api_key: str | None = None
    gemini_image_model: str = "gemini-2.5-flash-image"

    @field_validator("webhook_secret", mode="before")
    @classmethod
    def _check_secret(cls, v):
        if v in ("", None):
            return None
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", v):
            raise ValueError("WEBHOOK_SECRET faqat A-Z, a-z, 0-9, _ va - belgilaridan iborat, 16-256 uzunlikda bo'lishi kerak")
        return v

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        return v

    @field_validator("group_id", mode="before")
    @classmethod
    def _empty_group(cls, v):
        return None if v in ("", None) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
