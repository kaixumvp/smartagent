import pytest

from src.core.checkpointer import InMemoryCheckpointer


@pytest.mark.asyncio
async def test_save_and_load_roundtrip():
    cp = InMemoryCheckpointer()
    state = {"run_id": "r1", "messages": [{"role": "user", "content": "hi"}], "n": 1}
    await cp.save("r1", state)
    loaded = await cp.load("r1")
    assert loaded == state
    assert loaded is not state  # deep copy, not the same object


@pytest.mark.asyncio
async def test_load_missing_returns_none():
    cp = InMemoryCheckpointer()
    assert await cp.load("nope") is None


@pytest.mark.asyncio
async def test_load_is_isolated_from_later_mutation():
    cp = InMemoryCheckpointer()
    await cp.save("r1", {"messages": [{"role": "user", "content": "a"}]})

    loaded = await cp.load("r1")
    loaded["messages"][0]["content"] = "mutated"

    again = await cp.load("r1")
    assert again["messages"][0]["content"] == "a"  # snapshot not corrupted


@pytest.mark.asyncio
async def test_delete_and_list_runs():
    cp = InMemoryCheckpointer()
    await cp.save("r1", {})
    await cp.save("r2", {})
    assert set(await cp.list_runs()) == {"r1", "r2"}

    await cp.delete("r1")
    assert await cp.load("r1") is None
    assert await cp.list_runs() == ["r2"]
