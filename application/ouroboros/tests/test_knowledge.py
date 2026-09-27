import pytest

from conftest import FakeKnowledge, FakeLongTermMemory
from src.knowledge import KnowledgePlugin
from src.memory.consolidator import Consolidator
from src.memory.reflect import Reflector
from src.ports import InvokeContext, KnowledgeEntry


@pytest.mark.asyncio
async def test_knowledge_plugin_retrieves():
    store = FakeKnowledge([KnowledgeEntry(id="1", content="the answer is 42", source="docs", similarity=0.9)])
    plugin = KnowledgePlugin("kb", "search internal docs", store)

    out = await plugin.invoke(InvokeContext(), query="what is the answer")

    assert "the answer is 42" in out
    assert "docs" in out


def test_knowledge_plugin_manifest_namespace():
    store = FakeKnowledge()
    plugin = KnowledgePlugin("kb", "search docs", store)
    assert plugin.manifest.kind == "knowledge"
    assert plugin.manifest.function_name == "knowledge_kb"


def test_reflector_scores_preferences_higher():
    r = Reflector()
    assert r.score("ok") < r.score("I always prefer dark mode")


@pytest.mark.asyncio
async def test_consolidator_forgets_low_importance():
    store = FakeLongTermMemory()
    c = Consolidator(store, importance_threshold=0.5)

    inserted = await c.consolidate(None, "s1", "t1", "u1", [{"role": "user", "content": "ok"}])

    assert inserted == 0
    assert store.added == []


@pytest.mark.asyncio
async def test_consolidator_persists_high_importance():
    store = FakeLongTermMemory()
    c = Consolidator(store, importance_threshold=0.5)

    inserted = await c.consolidate(
        None, "s1", "t1", "u1", [{"role": "user", "content": "I always prefer dark mode"}]
    )

    assert inserted == 1
    assert store.items[0].importance > 0.5
