"""Tests for HTTP/MCP tools with httpx.AsyncClient mocked out."""

import httpx
import pytest

from src.tools.builtin.http import HttpTool
from src.tools.http_openapi import HttpOpenApiTool
from src.tools.mcp import McpClient, McpTool


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self._text = text
        self._json = json_data

    @property
    def is_success(self):
        return self.status_code < 400

    @property
    def text(self):
        return self._text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json if self._json is not None else {}


class _FakeAsyncClient:
    response = _FakeResponse()
    last = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, **kw):
        _FakeAsyncClient.last = (method, url, kw)
        return _FakeAsyncClient.response

    async def get(self, url, **kw):
        _FakeAsyncClient.last = ("GET", url, kw)
        return _FakeAsyncClient.response

    async def post(self, url, **kw):
        _FakeAsyncClient.last = ("POST", url, kw)
        return _FakeAsyncClient.response


# --------------------------------------------------------------------------- HttpTool
@pytest.mark.asyncio
async def test_http_tool_success(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, "hello world")

    tool = HttpTool()
    r = await tool.run(url="https://x", method="GET")
    assert r.success
    assert r.output == "hello world"


@pytest.mark.asyncio
async def test_http_tool_error(monkeypatch):
    class _Raising(_FakeAsyncClient):
        async def request(self, *a, **kw):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Raising)
    tool = HttpTool()
    r = await tool.run(url="https://x")
    assert not r.success
    assert "connection refused" in r.error


# --------------------------------------------------------------------------- HttpOpenApiTool
@pytest.mark.asyncio
async def test_http_openapi_tool_formats_url_and_headers(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, '{"ok": true}')

    tool = HttpOpenApiTool(
        id_="t1", name="orders", description="d", parameters={},
        permission="read", url_template="https://api/orders/{id}", method="GET",
        config={"headers": {"X-Key": "v"}},
    )
    r = await tool.run(id="123")
    assert r.success

    method, url, kw = _FakeAsyncClient.last
    assert method == "GET"
    assert url == "https://api/orders/123"
    assert kw["headers"]["X-Key"] == "v"


@pytest.mark.asyncio
async def test_http_openapi_tool_injects_api_key(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, "ok")

    tool = HttpOpenApiTool(
        id_="t1", name="o", description="d", parameters={},
        permission="read", url_template="https://api/o", method="POST",
        config={"auth": {"type": "api_key", "header": "X-Api-Key", "key": "secret"}},
    )
    await tool.run()
    _, _, kw = _FakeAsyncClient.last
    assert kw["headers"]["X-Api-Key"] == "secret"


# --------------------------------------------------------------------------- McpClient / McpTool
@pytest.mark.asyncio
async def test_mcp_rpc_returns_result(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, json_data={"result": {"content": [{"type": "text", "text": "hi"}]}})

    client = McpClient("https://mcp")
    result = await client._rpc("initialize", {})
    assert result["content"][0]["text"] == "hi"


@pytest.mark.asyncio
async def test_mcp_rpc_raises_on_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, json_data={"error": {"code": -1, "message": "bad"}})

    client = McpClient("https://mcp")
    with pytest.raises(RuntimeError, match="MCP error"):
        await client._rpc("initialize", {})


@pytest.mark.asyncio
async def test_mcp_call_tool_joins_text_blocks(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, json_data={
        "result": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    })

    client = McpClient("https://mcp")
    out = await client.call_tool("foo", {"x": 1})
    assert out == "a\nb"


@pytest.mark.asyncio
async def test_mcp_tool_run_success(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = _FakeResponse(200, json_data={"result": {"content": [{"type": "text", "text": "result"}]}})

    tool = McpTool(id_="t", name="foo", description="d", parameters={}, permission="read", endpoint="https://mcp")
    r = await tool.run(x=1)
    assert r.success
    assert r.output == "result"


@pytest.mark.asyncio
async def test_mcp_tool_run_error(monkeypatch):
    class _Raising(_FakeAsyncClient):
        async def post(self, *a, **kw):
            raise RuntimeError("mcp down")

    monkeypatch.setattr(httpx, "AsyncClient", _Raising)
    tool = McpTool(id_="t", name="foo", description="d", parameters={}, permission="read", endpoint="https://mcp")
    r = await tool.run(x=1)
    assert not r.success
    assert "mcp down" in r.error
