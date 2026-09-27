import logging
import sys
from pathlib import Path

# Let pytest import the src package without installing it.
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.llm.base import LLMResponse, Usage  # noqa: E402
from src.plugins.registry import PluginRegistry  # noqa: E402
from src.ports import KnowledgeEntry, LongTermMemory, MemoryEntry, WorkingMemory  # noqa: E402
from src.tools.registry import build_default_registry  # noqa: E402


def pytest_configure(config):
    """Emit all framework logs; the displayed level is controlled by pytest's --log-cli-level."""
    logger = logging.getLogger("src")
    logger.setLevel(logging.DEBUG)
    logger.propagate = True


class MockLLMGateway:
    """Programmable mock LLM: pops preset responses in order."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses: list[LLMResponse] = list(responses or [])
        self.calls: list[dict] = []

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="", usage=Usage())


class FakeWorkingMemory(WorkingMemory):
    """In-memory WorkingMemory so tests don't depend on Redis."""

    def __init__(self) -> None:
        self.history: dict[str, list[dict]] = {}

    async def get_history(self, session_id: str) -> list[dict]:
        return list(self.history.get(session_id, []))

    async def append(self, session_id: str, message: dict) -> None:
        self.history.setdefault(session_id, []).append(message)


class FakeLongTermMemory(LongTermMemory):
    """In-memory LongTermMemory. `recall` matches by exact content by default; override for dedup tests."""

    def __init__(self, items: list[MemoryEntry] | None = None) -> None:
        self.items: list[MemoryEntry] = list(items or [])
        self.added: list[str] = []

    async def add(self, db, *, tenant_id, user_id, session_id, content,
                  importance=0.5, confidence=0.5) -> str:
        self.added.append(content)
        self.items.append(MemoryEntry(
            id=f"mem_{len(self.items)}",
            tenant_id=tenant_id, user_id=user_id, session_id=session_id,
            content=content, importance=importance, confidence=confidence,
        ))
        return f"mem_{len(self.items) - 1}"

    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]:
        return [m for m in self.items if m.content == query][:top_k]


def build_default_plugin_registry() -> PluginRegistry:
    """Wrap the builtin tools into a PluginRegistry for runtime tests."""
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)
    return registry


def build_default_plugins() -> list:
    """Builtin tools wrapped as Plugin objects (for AgentDefinition.plugins)."""
    return build_default_plugin_registry().all()


class FakeKnowledge:
    """In-memory Knowledge/Retriever for knowledge-port tests."""

    def __init__(self, docs: list[KnowledgeEntry] | None = None) -> None:
        self.docs: list[KnowledgeEntry] = list(docs or [])
        self.added: list[str] = []

    async def search(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        return self.docs[:top_k]

    async def retrieve(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        return self.docs[:top_k]

    async def add(self, *, content: str, source: str | None = None, metadata: dict | None = None) -> str:
        self.added.append(content)
        return str(len(self.added))
