import pytest

from app import embedding
from app.embedding import build_embedder


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"index": 0, "embedding": [0.1] * 1024}]}


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return _FakeResponse()


def test_build_embedder_hash_keeps_dim():
    assert build_embedder("hash", 256).dim == 256


def test_build_embedder_http_requires_url():
    with pytest.raises(ValueError):
        build_embedder("http", 256)


def test_build_embedder_http_detects_real_dim(monkeypatch):
    monkeypatch.setattr(embedding.httpx, "Client", _FakeClient)
    embedder = build_embedder("http", 256, url="http://fake/v1/embeddings", model="m")
    assert embedder.dim == 1024
