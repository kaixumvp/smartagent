import json

from redis.asyncio import Redis


class WorkingBrain:
    """Session-level working memory (V0.1 simplified): Redis stores the most recent
    window_size messages with a 24h TTL.

    Key = wb:{session_id}:messages, value is a JSON list of messages.
    No consolidation/recall/forgetting (from V0.2 onward).
    """

    def __init__(self, redis: Redis, window_size: int = 20, ttl_seconds: int = 24 * 3600) -> None:
        self._redis = redis
        self._window_size = window_size
        self._ttl = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        return f"wb:{session_id}:messages"

    async def get_history(self, session_id: str) -> list[dict]:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    async def append(self, session_id: str, message: dict) -> None:
        history = await self.get_history(session_id)
        history.append(message)
        history = history[-self._window_size:]
        await self._redis.set(self._key(session_id), json.dumps(history, ensure_ascii=False), ex=self._ttl)
