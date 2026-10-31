"""aiogram FSM holatlarini ma'lumotlar bazasida saqlash (Vercel kabi serverless muhit uchun)."""
import json
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.ext.asyncio import async_sessionmaker

from .models import FsmRecord
from .session import get_sessionmaker


class DbStorage(BaseStorage):
    def __init__(self, sessionmaker: async_sessionmaker | None = None):
        self._sm = sessionmaker

    @property
    def sm(self) -> async_sessionmaker:
        return self._sm or get_sessionmaker()

    @staticmethod
    def _key(key: StorageKey) -> str:
        parts = [key.bot_id, key.chat_id, key.user_id, key.thread_id or "", key.business_connection_id or "", key.destiny]
        return ":".join(map(str, parts))

    async def _upsert(self, key: StorageKey, **values: Any) -> None:
        async with self.sm() as s:
            rec = await s.get(FsmRecord, self._key(key))
            if rec is None:
                rec = FsmRecord(key=self._key(key), state=None, data="{}")
                s.add(rec)
            for k, v in values.items():
                setattr(rec, k, v)
            await s.commit()

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        await self._upsert(key, state=value)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.sm() as s:
            rec = await s.get(FsmRecord, self._key(key))
            return rec.state if rec else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(key, data=json.dumps(dict(data), ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.sm() as s:
            rec = await s.get(FsmRecord, self._key(key))
            return json.loads(rec.data) if rec and rec.data else {}

    async def close(self) -> None:
        pass
