import asyncio
from types import SimpleNamespace

import pytest

from app import api_tool_executor
from app.api_tool_executor import ApiToolCallError


def test_render_path_encodes_path_arguments():
    assert api_tool_executor._render_path("/users/{user_id}", {"user_id": "a/b"}) == "/users/a%2Fb"


def test_render_path_requires_scalar_arguments():
    with pytest.raises(ApiToolCallError, match="missing or is not scalar"):
        api_tool_executor._render_path("/users/{user_id}", {"user_id": {"id": 1}})


def test_render_path_rejects_an_absolute_url():
    with pytest.raises(ApiToolCallError, match="relative path"):
        api_tool_executor._render_path("//other.example/path", {})


def test_tool_cannot_override_authentication_or_host_headers():
    for name in ("Authorization", "Host", "Proxy-Authorization"):
        with pytest.raises(ApiToolCallError, match="cannot be set"):
            api_tool_executor._render_headers({name: "value"}, {})


def test_input_template_resolves_nested_values_and_preserves_types():
    value = api_tool_executor._resolve_input_value(
        {"include": "$input.options.include", "fixed": "yes"},
        {"options": {"include": True}},
    )
    assert value == {"include": True, "fixed": "yes"}


def test_service_url_rejects_plain_http_without_private_network_opt_in():
    with pytest.raises(ValueError, match="HTTPS is required"):
        api_tool_executor.validate_service_url("http://api.example.com", False)


def test_service_url_rejects_embedded_credentials_and_query():
    with pytest.raises(ValueError):
        api_tool_executor.validate_service_url("https://user:pass@example.com/api", False)
    with pytest.raises(ValueError):
        api_tool_executor.validate_service_url("https://example.com/api?token=value", True)


def test_public_service_rejects_non_public_dns_results(monkeypatch):
    monkeypatch.setattr(
        api_tool_executor.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(ApiToolCallError, match="non-public address"):
        asyncio.run(api_tool_executor._validate_resolved_host("public.example", False))


def test_api_tool_maps_arguments_and_returns_structured_result(monkeypatch):
    requests = {}

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        is_success = True

        async def aiter_bytes(self):
            yield b'{"ok":true,"city":"Hangzhou"}'

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            requests["client_options"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, **kwargs):
            requests.update(method=method, url=url, **kwargs)
            return FakeStream()

    async def allow_host(*args):
        return None

    async def prepare_endpoint(url, auth_type, config):
        return url, {}

    monkeypatch.setattr(api_tool_executor, "_validate_resolved_host", allow_host)
    monkeypatch.setattr(api_tool_executor, "decrypt_auth_config", lambda value: {})
    monkeypatch.setattr(api_tool_executor, "prepare_mcp_endpoint", prepare_endpoint)
    monkeypatch.setattr(api_tool_executor.httpx, "AsyncClient", FakeClient)
    service = SimpleNamespace(
        enabled=True,
        base_url="https://api.example.com/v1",
        allow_private_network=False,
        request_timeout_seconds=12,
        auth_config_encrypted=None,
        auth_type="none",
    )
    tool = SimpleNamespace(
        manifest={
            "execution": {
                "kind": "http",
                "method": "POST",
                "path": "/weather/{city}",
                "query_template": {"units": "metric", "locale": "$input.locale"},
                "header_template": {"X-Tenant": "$input.tenant"},
                "body_template": {"city": "$input.city", "include": "$input.include"},
            }
        }
    )

    result = asyncio.run(
        api_tool_executor.call_api_tool(
            service,
            tool,
            {"city": "Hangzhou", "locale": "zh-CN", "tenant": "demo", "include": True},
        )
    )

    assert requests["method"] == "POST"
    assert requests["url"] == "https://api.example.com/v1/weather/Hangzhou"
    assert requests["params"] == {"units": "metric", "locale": "zh-CN"}
    assert requests["headers"] == {"X-Tenant": "demo"}
    assert requests["json"] == {"city": "Hangzhou", "include": True}
    assert requests["client_options"]["follow_redirects"] is False
    assert requests["client_options"]["trust_env"] is False
    assert result["structuredContent"] == {"ok": True, "city": "Hangzhou"}
