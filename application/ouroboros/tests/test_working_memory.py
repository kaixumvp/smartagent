"""Tests for the Redis-backed Working Brain, using a fake Redis."""

import pytest

from src.memory.working import WorkingBrain


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


@pytest.mark.asyncio
async def test_working_brain_empty():
    brain = WorkingBrain(FakeRedis())
    assert await brain.get_history("s1") == []


@pytest.mark.asyncio
async def test_working_brain_append_and_window_truncation():
    brain = WorkingBrain(FakeRedis(), window_size=2)
    await brain.append("s1", {"role": "user", "content": "a"})
    await brain.append("s1", {"role": "user", "content": "b"})
    await brain.append("s1", {"role": "user", "content": "c"})

    hist = await brain.get_history("s1")
    assert [m["content"] for m in hist] == ["b", "c"]  # keeps the last window_size messages


@pytest.mark.asyncio
async def test_working_brain_corrupt_json_returns_empty():
    redis = FakeRedis()
    redis.store["wb:s1:messages"] = "not-json"
    brain = WorkingBrain(redis)
    assert await brain.get_history("s1") == []
