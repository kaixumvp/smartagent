import math

import pytest

from src.llm.base import LLMResponse, ToolCall, Usage
from src.llm.embedder import HashEmbedder


def test_llm_response_defaults():
    r = LLMResponse()
    assert r.content is None
    assert r.tool_calls == []
    assert r.usage.total_tokens == 0


def test_tool_call_defaults():
    tc = ToolCall(name="calculator")
    assert tc.id == ""
    assert tc.arguments == {}


def test_usage_defaults():
    u = Usage()
    assert u.prompt_tokens == 0 and u.completion_tokens == 0 and u.total_tokens == 0


@pytest.mark.asyncio
async def test_hash_embedder_fixed_dimension():
    e = HashEmbedder(64)
    v = (await e.embed(["hello world"]))[0]
    assert len(v) == 64


@pytest.mark.asyncio
async def test_hash_embedder_deterministic():
    e = HashEmbedder(16)
    a = await e.embed(["hello world"])
    b = await e.embed(["hello world"])
    assert a == b


@pytest.mark.asyncio
async def test_hash_embedder_unit_norm():
    e = HashEmbedder(32)
    v = (await e.embed(["hello world"]))[0]
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6
