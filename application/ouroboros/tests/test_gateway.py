"""Tests for the LiteLLM gateway and embedder, with litellm mocked out."""

import litellm
import pytest

from src.llm.embedder import LiteLLMEmbedder
from src.llm.litellm_gateway import LiteLLMGateway


class _FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeCompletionResponse:
    def __init__(self, content=None, tool_calls=None, usage=None):
        self.choices = [_FakeChoice(_FakeMessage(content, tool_calls))]
        self.usage = usage if usage is not None else _FakeUsage()


class _FakeEmbedResponse:
    def __init__(self, embeddings):
        self.data = [{"embedding": e} for e in embeddings]


@pytest.mark.asyncio
async def test_litellm_gateway_chat_with_tool_calls(monkeypatch):
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _FakeCompletionResponse(
            content=None,
            tool_calls=[_FakeToolCall("c1", "calculator", '{"expression": "1+1"}')],
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    gw = LiteLLMGateway(model="deepseek", api_key="sk-1", api_base="https://api")
    resp = await gw.chat(messages=[{"role": "user", "content": "hi"}], model="deepseek", tools=[{"type": "function"}])

    assert resp.tool_calls[0].name == "calculator"
    assert resp.tool_calls[0].arguments == {"expression": "1+1"}
    assert resp.usage.total_tokens == 15
    assert captured["api_key"] == "sk-1"
    assert captured["api_base"] == "https://api"


@pytest.mark.asyncio
async def test_litellm_gateway_chat_plain_without_key(monkeypatch):
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _FakeCompletionResponse(content="answer")

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    gw = LiteLLMGateway(model="deepseek")  # no api_key / api_base
    resp = await gw.chat(messages=[{"role": "user", "content": "hi"}], model="deepseek")

    assert resp.content == "answer"
    assert resp.tool_calls == []
    assert "api_key" not in captured
    assert "api_base" not in captured


@pytest.mark.asyncio
async def test_litellm_gateway_bad_arguments_json(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _FakeCompletionResponse(
            tool_calls=[_FakeToolCall("c1", "calc", "not-json")],
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    gw = LiteLLMGateway(model="m")
    resp = await gw.chat(messages=[{"role": "user", "content": "hi"}])
    assert resp.tool_calls[0].arguments == {}


@pytest.mark.asyncio
async def test_litellm_embedder(monkeypatch):
    captured: dict = {}

    async def fake_aembedding(**kwargs):
        captured.update(kwargs)
        return _FakeEmbedResponse([[0.1, 0.2, 0.3]])

    monkeypatch.setattr(litellm, "aembedding", fake_aembedding)

    e = LiteLLMEmbedder("text-embedding-3-small", api_key="sk", api_base="https://api")
    vecs = await e.embed(["hello"])

    assert vecs == [[0.1, 0.2, 0.3]]
    assert captured["model"] == "text-embedding-3-small"
