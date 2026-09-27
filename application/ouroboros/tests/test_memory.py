import pytest

from conftest import FakeLongTermMemory, FakeWorkingMemory
from src.memory.consolidator import Consolidator
from src.memory.manager import MemoryManager
from src.ports import MemoryEntry


def test_consolidator_extracts_user_and_final_answer():
    mem = FakeLongTermMemory()
    c = Consolidator(mem, similarity_threshold=0.85)
    history = [
        {"role": "user", "content": "用户偏好简洁"},
        {"role": "assistant", "content": "好的"},
    ]
    assert c._extract(history) == ["用户偏好简洁", "好的"]


@pytest.mark.asyncio
async def test_consolidator_skips_near_duplicate():
    existing = MemoryEntry(id="m0", tenant_id="t", content="偏好简洁", similarity=0.9)
    mem = FakeLongTermMemory([existing])
    c = Consolidator(mem, similarity_threshold=0.85)

    n = await c.consolidate(None, "s1", "t", "u", [{"role": "user", "content": "偏好简洁"}])
    assert n == 0
    assert mem.added == []


@pytest.mark.asyncio
async def test_consolidator_inserts_new():
    mem = FakeLongTermMemory()
    c = Consolidator(mem, similarity_threshold=0.85)

    n = await c.consolidate(None, "s1", "t", "u", [{"role": "user", "content": "新的事实"}])
    assert n == 1
    assert mem.added == ["新的事实"]


@pytest.mark.asyncio
async def test_memory_manager_facade():
    working = FakeWorkingMemory()
    longterm = FakeLongTermMemory()
    mgr = MemoryManager(working, longterm, Consolidator(longterm, similarity_threshold=0.85))

    await mgr.write("s1", {"role": "user", "content": "hi"})
    assert await mgr.get_history("s1") == [{"role": "user", "content": "hi"}]

    # recall delegates to long-term memory (empty here)
    assert await mgr.recall(None, "t", "u", "x", 5) == []

    # consolidate reads working history and persists the user statement
    n = await mgr.consolidate(None, "s1", "t", "u")
    assert n == 1
    assert longterm.added == ["hi"]
