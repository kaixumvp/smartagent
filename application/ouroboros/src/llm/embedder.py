"""Embedding providers for long-term (Vector) memory.

The `build_embedder` factory (which reads host settings) lives in the business layer; the
framework ships only the protocol and the concrete LiteLLM / offline-hash implementations.
"""

import hashlib
import math
import re

import litellm

from src.ports import Embedder

__all__ = ["Embedder", "LiteLLMEmbedder", "HashEmbedder"]


class LiteLLMEmbedder:
    """LiteLLM-backed embedder (OpenAI-compatible embedding models, e.g. text-embedding-3-small)."""

    def __init__(self, model: str, api_key: str = "", api_base: str | None = None) -> None:
        self._model = model
        self._api_key = api_key
        self._api_base = api_base

    async def embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict = {"model": self._model, "input": texts}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        resp = await litellm.aembedding(**kwargs)
        return [list(d["embedding"]) for d in resp.data]


class HashEmbedder:
    """Deterministic feature-hashing embedder used as an offline fallback.

    Produces stable, dimension-fixed vectors so cosine-similarity dedup behaves consistently
    without an embedding API. Not intended for production semantic recall.
    """

    def __init__(self, dimension: int = 1536) -> None:
        self._dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        for token in re.findall(r"\w+", text.lower()):
            digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)  # noqa: S324
            idx = digest % self._dimension
            sign = 1.0 if (digest >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
