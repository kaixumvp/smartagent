from __future__ import annotations

from typing import Protocol

import httpx

from .textutil import hashed_embedding


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hashed_embedding(text, self.dim) for text in texts]


class HttpEmbedder:
    """OpenAI-compatible embeddings endpoint (optional)."""

    def __init__(self, url: str, model: str, api_key: str = "", dim: int = 256) -> None:
        self.url = url
        self.model = model
        self.api_key = api_key
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "input": texts}
        with httpx.Client(timeout=60) as client:
            response = client.post(self.url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()["data"]
            vectors = [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
        if vectors:
            self.dim = len(vectors[0])
        return vectors


def build_embedder(kind: str, dim: int, url: str = "", model: str = "", api_key: str = "") -> Embedder:
    if kind == "http":
        if not url:
            raise ValueError("EMBEDDING_URL is required when EMBEDDER=http")
        embedder = HttpEmbedder(url, model or "embedding", api_key, dim)
        # 探测一次真实向量维度，让 build_index 用 embedder.dim 建集时尺寸正确
        probe = embedder.embed(["__dim_probe__"])
        embedder.dim = len(probe[0]) if probe else dim
        return embedder
    return HashEmbedder(dim)
