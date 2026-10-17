import asyncio
import logging
from types import SimpleNamespace

import pytest

from app import api_tool_executor
from app.api_tool_executor import (
    ApiToolBlockedError,
    ApiToolCallError,
    ApiToolConfigError,
    ApiToolRequestError,
    ApiToolTimeoutError,
)


def test_render_path_encodes_path_arguments():
    assert api_tool_executor._render_path("/users/{user_id}", {"user_id": "a/b"}) == "/users/a%2Fb"


def test_render_path_requires_scalar_arguments():
    with pytest.raises(ApiToolRequestError, match="missing or is not scalar"):
        api_tool_executor._render_path("/users/{user_id}", {"user_id": {"id": 1}})


def test_render_path_rejects_an_absolute_url():
    with pytest.raises(ApiToolConfigError, match="relative path"):
        api_tool_executor._render_path("//other.example/path", {})


def test_tool_cannot_override_authentication_or_host_headers():
    for name in ("Authorization", "Host", "Proxy-Authorization"):
        with pytest.raises(ApiToolConfigError, match="cannot be set"):
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
    with pytest.raises(ApiToolBlockedError, match="non-public address"):
        asyncio.run(api_tool_executor._validate_resolved_host("public.example", False))


def test_api_tool_maps_arguments_and_returns_structured_result(monkeypatch):
    requests = {}

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        is_success = True
        headers = {"content-type": "application/json"}

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


def test_error_classes_carry_the_status_code_used_by_the_routers():
    # Router 直接返回 exc.status_code，不再靠字符串匹配判断
    assert ApiToolCallError.status_code == 502  # 远端返回非 2xx、连接失败、响应超限
    assert ApiToolRequestError.status_code == 400  # 调用方入参不满足契约
    assert ApiToolConfigError.status_code == 422  # Tool / Service 存储定义不可用
    assert ApiToolBlockedError.status_code == 403  # 网络策略拒绝
    assert ApiToolTimeoutError.status_code == 504  # 超时
    for error_class in (
        ApiToolRequestError,
        ApiToolConfigError,
        ApiToolBlockedError,
        ApiToolTimeoutError,
    ):
        assert issubclass(error_class, ApiToolCallError)


def _stub_execution_environment(monkeypatch, status_code=200, body=b"{}", auth_headers=None):
    """把远端调用换成假客户端，只关心错误分类。"""

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.encoding = "utf-8"
            self.is_success = 200 <= status_code < 300
            self.headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield body

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, **kwargs):
            return FakeStream()

    async def allow_host(*args):
        return None

    async def prepare_endpoint(url, auth_type, config):
        return url, dict(auth_headers or {})

    monkeypatch.setattr(api_tool_executor, "_validate_resolved_host", allow_host)
    monkeypatch.setattr(api_tool_executor, "decrypt_auth_config", lambda value: {})
    monkeypatch.setattr(api_tool_executor, "prepare_mcp_endpoint", prepare_endpoint)
    monkeypatch.setattr(api_tool_executor.httpx, "AsyncClient", FakeClient)
    return SimpleNamespace(
        enabled=True,
        base_url="https://api.example.com/v1",
        allow_private_network=False,
        request_timeout_seconds=12,
        auth_config_encrypted=None,
        auth_type="none",
    )


def _tool_with_execution(execution):
    return SimpleNamespace(
        id="tool_test",
        display_name="天气查询",
        manifest={"execution": execution},
    )


def test_missing_tool_input_is_reported_as_a_request_error(monkeypatch):
    service = _stub_execution_environment(monkeypatch)
    tool = _tool_with_execution(
        {
            "kind": "http",
            "method": "POST",
            "path": "/weather",
            "body_template": {"city": "$input.city"},
        }
    )

    with pytest.raises(ApiToolRequestError, match="Required Tool input 'city' is missing"):
        asyncio.run(api_tool_executor.call_api_tool(service, tool, {}))


def test_unusable_tool_definition_is_reported_as_a_config_error(monkeypatch):
    service = _stub_execution_environment(monkeypatch)
    tool = _tool_with_execution({"kind": "mcp", "method": "POST", "path": "/weather"})

    with pytest.raises(ApiToolConfigError, match="no valid HTTP execution configuration"):
        asyncio.run(api_tool_executor.call_api_tool(service, tool, {}))


def test_remote_non_2xx_stays_a_bad_gateway(monkeypatch):
    service = _stub_execution_environment(monkeypatch, status_code=404)
    tool = _tool_with_execution({"kind": "http", "method": "GET", "path": "/weather"})

    with pytest.raises(ApiToolCallError, match="returned HTTP 404") as excinfo:
        asyncio.run(api_tool_executor.call_api_tool(service, tool, {}))

    assert type(excinfo.value) is ApiToolCallError
    assert excinfo.value.status_code == 502


def test_http_log_redacts_credentials_but_keeps_context():
    headers = api_tool_executor._redact_headers(
        {
            "Authorization": "Bearer secret-token",
            "X-API-Key": "secret-key",
            "Cookie": "session=secret-session",
            "X-Tenant": "demo",
        }
    )
    assert headers["Authorization"] == "Bearer <redacted>"
    assert headers["X-API-Key"] == "<redacted>"
    assert headers["Cookie"] == "<redacted>"
    assert headers["X-Tenant"] == "demo"

    url = api_tool_executor._redact_url(
        "https://api.example.com/search?api_key=secret-key&access_token=secret-token&city=Hangzhou"
    )
    assert url == (
        "https://api.example.com/search"
        "?api_key=<redacted>&access_token=<redacted>&city=Hangzhou"
    )


def test_http_log_preview_truncates_large_bodies():
    preview = api_tool_executor._preview(
        {"blob": "x" * (api_tool_executor.MAX_LOG_BODY_CHARS * 2)}
    )
    assert preview.endswith("已截断）")
    assert len(preview) < api_tool_executor.MAX_LOG_BODY_CHARS * 2
    assert api_tool_executor._preview(None) == "<无>"


def test_call_api_tool_logs_outbound_request_without_leaking_credentials(monkeypatch, caplog):
    service = _stub_execution_environment(
        monkeypatch, auth_headers={"Authorization": "Bearer secret-token"}
    )
    service.auth_type = "bearer"
    tool = _tool_with_execution(
        {
            "kind": "http",
            "method": "POST",
            "path": "/weather",
            "query_template": {"api_key": "secret-query-key", "units": "metric"},
            "body_template": {"city": "$input.city"},
        }
    )

    with caplog.at_level(logging.INFO, logger="app.api_tool_executor"):
        result = asyncio.run(
            api_tool_executor.call_api_tool(service, tool, {"city": "Hangzhou"})
        )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "API Tool 出站请求" in messages
    assert "Bearer <redacted>" in messages
    assert "secret-token" not in messages
    assert "secret-query-key" not in messages  # query 里的密钥同样不能进日志
    assert "api_key=<redacted>" in messages
    assert "units=metric" in messages
    assert "Hangzhou" in messages
    assert result["statusCode"] == 200


def test_call_api_tool_logs_the_remote_body_on_non_2xx(monkeypatch, caplog):
    service = _stub_execution_environment(monkeypatch, status_code=404, body=b'{"msg":"not found"}')
    tool = _tool_with_execution({"kind": "http", "method": "GET", "path": "/weather"})

    with caplog.at_level(logging.INFO, logger="app.api_tool_executor"):
        with pytest.raises(ApiToolCallError, match="returned HTTP 404"):
            asyncio.run(api_tool_executor.call_api_tool(service, tool, {}))

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "HTTP 404" in messages
    assert "not found" in messages  # 远端错误体进日志，便于排查


def _install_recording_client(monkeypatch, requests: dict, status_code: int = 200, body: bytes = b"{}"):
    """不桩认证的假客户端：记录真正发出的 method / url / headers。"""

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.encoding = "utf-8"
            self.is_success = 200 <= status_code < 300
            self.headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield body

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, headers=None, **kwargs):
            requests.update(method=method, url=url, headers=headers or {}, **kwargs)
            return FakeStream()

    async def allow_host(*args):
        return None

    monkeypatch.setattr(api_tool_executor, "_validate_resolved_host", allow_host)
    monkeypatch.setattr(api_tool_executor.httpx, "AsyncClient", FakeClient)


def _expiring_jwt(exp_offset_seconds: int) -> str:
    import base64
    import json
    from datetime import datetime, timezone

    def segment(payload: dict) -> str:
        raw = json.dumps(payload).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    exp = int(datetime.now(timezone.utc).timestamp()) + exp_offset_seconds
    return f"{segment({'alg': 'HS256'})}.{segment({'sub': 'tester', 'exp': exp})}.signature"


def _bearer_service(**overrides):
    values = dict(
        enabled=True,
        base_url="https://api.example.com/v1",
        allow_private_network=False,
        request_timeout_seconds=12,
        auth_config_encrypted="encrypted",
        auth_type="bearer",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_outbound_authorization_uses_a_single_bearer_prefix(monkeypatch):
    """P0 端到端回归：存量数据存的是 'Bearer xxx'，发出去只能是单层前缀。"""
    requests: dict = {}
    _install_recording_client(monkeypatch, requests)
    monkeypatch.setattr(
        api_tool_executor, "decrypt_auth_config", lambda value: {"token": "Bearer eyJ.stored"}
    )
    tool = _tool_with_execution({"kind": "http", "method": "GET", "path": "/weather"})

    asyncio.run(api_tool_executor.call_api_tool(_bearer_service(), tool, {}))

    assert requests["headers"]["Authorization"] == "Bearer eyJ.stored"


def test_expired_bearer_token_surfaces_as_a_config_error(monkeypatch):
    requests: dict = {}
    _install_recording_client(monkeypatch, requests)
    monkeypatch.setattr(
        api_tool_executor, "decrypt_auth_config", lambda value: {"token": _expiring_jwt(-120)}
    )
    tool = _tool_with_execution({"kind": "http", "method": "GET", "path": "/weather"})

    with pytest.raises(ApiToolConfigError, match="已过期"):
        asyncio.run(api_tool_executor.call_api_tool(_bearer_service(), tool, {}))

    assert requests == {}  # 过期凭据不发请求


def test_bearer_token_endpoint_is_checked_against_the_network_policy(monkeypatch):
    requests: dict = {}
    _install_recording_client(monkeypatch, requests)
    monkeypatch.setattr(
        api_tool_executor,
        "decrypt_auth_config",
        lambda value: {"token_endpoint": "http://10.0.0.5/token"},
    )
    tool = _tool_with_execution({"kind": "http", "method": "GET", "path": "/weather"})

    # 未开启私网访问时，明文 HTTP 的 token 端点要在发请求前就被拦下
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(api_tool_executor.call_api_tool(_bearer_service(), tool, {}))
    assert requests == {}
