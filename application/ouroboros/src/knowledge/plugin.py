"""Knowledge-as-a-plugin (V0.3).

Wraps a host-provided ``Retriever``/``Knowledge`` port as a ``Plugin`` with ``kind="knowledge"``
so the LLM can call it like any other tool. The framework only *retrieves*; the RAG pipeline
(ingest/chunk/embed/rerank) lives entirely in the host.
"""

from __future__ import annotations

import json
from typing import Any

from src.plugins.base import InvokeContext
from src.ports import PluginManifest, Retriever

_QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "Natural-language search query"}},
    "required": ["query"],
}


class KnowledgePlugin:
    """A retrievable knowledge source exposed to the LLM as a callable plugin."""

    kind = "knowledge"

    def __init__(
        self,
        name: str,
        description: str,
        retriever: Retriever,
        *,
        top_k: int = 5,
        permission: str = "read",
    ) -> None:
        self._name = name
        self._retriever = retriever
        self._top_k = top_k
        self._manifest = PluginManifest(
            name=name,
            version="1",
            kind="knowledge",
            description=description,
            parameters=_QUERY_SCHEMA,
            permission=permission,
        )

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    async def setup(self, config: dict) -> None:
        return None

    async def teardown(self) -> None:
        return None

    async def invoke(self, ctx: InvokeContext, **kw: Any) -> str:
        query = str(kw.get("query") or kw.get("q") or (json.dumps(kw, ensure_ascii=False) if kw else ""))
        entries = await self._retriever.retrieve(query, top_k=self._top_k)
        return json.dumps(
            [
                {
                    "content": e.content,
                    "source": e.source,
                    "similarity": e.similarity,
                }
                for e in entries
            ],
            ensure_ascii=False,
        )


__all__ = ["KnowledgePlugin"]
