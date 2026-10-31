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
