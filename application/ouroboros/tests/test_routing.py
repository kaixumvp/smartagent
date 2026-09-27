import pytest

from src.llm.base import LLMResponse, Usage
from src.llm.routing import FallbackLLMGateway, FaultTolerantGateway


class FailingGateway:
    async def chat(self, messages, model=None, tools=None):
        raise RuntimeError("down")


class OkGateway:
    def __init__(self, name: str = "ok"):
        self._model = name

    async def chat(self, messages, model=None, tools=None):
        return LLMResponse(content="hi", usage=Usage())


@pytest.mark.asyncio
async def test_fallback_uses_next_gateway_on_failure():
    g = FallbackLLMGateway([FailingGateway(), OkGateway()])
    resp = await g.chat([], model="m")
    assert resp.content == "hi"
    assert g.last_used == "ok"


@pytest.mark.asyncio
async def test_fallback_raises_when_all_fail():
    g = FallbackLLMGateway([FailingGateway(), FailingGateway()])
    with pytest.raises(RuntimeError):
        await g.chat([])


def test_fallback_requires_at_least_one_gateway():
    with pytest.raises(ValueError):
        FallbackLLMGateway([])


@pytest.mark.asyncio
async def test_fault_tolerant_returns_empty_on_error():
    g = FaultTolerantGateway(FailingGateway())
    resp = await g.chat([])
    assert resp.content == ""
    assert resp.tool_calls == []


@pytest.mark.asyncio
async def test_fault_tolerant_normalizes_none_tool_calls():
    class BadToolCalls:
        async def chat(self, messages, model=None, tools=None):
            resp = LLMResponse(content="x")
            resp.tool_calls = None
            return resp

    g = FaultTolerantGateway(BadToolCalls())
    resp = await g.chat([])
    assert resp.tool_calls == []
