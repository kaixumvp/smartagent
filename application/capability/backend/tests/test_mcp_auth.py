import asyncio
import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from redis.exceptions import RedisError

from app import mcp_auth, token_cache
from app.mcp_auth import AuthConfigError, AuthNegotiationError


def _jwt(exp_offset_seconds: int | None) -> str:
    def segment(payload: dict) -> str:
        raw = json.dumps(payload).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    claims: dict = {"sub": "tester"}
    if exp_offset_seconds is not None:
        claims["exp"] = int(datetime.now(timezone.utc).timestamp()) + exp_offset_seconds
    return f"{segment({'alg': 'HS256'})}.{segment(claims)}.signature"


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeTokenClient:
    """记录发往 token 端点的请求，返回预置响应。"""

    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requests: list[dict] = []

    def __call__(self, **kwargs) -> "_FakeTokenClient":
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json=None, data=None, headers=None):
        self.requests.append({"url": url, "json": json, "data": data, "headers": headers or {}})
        return self.response

    async def get(self, url, params=None, headers=None):
        self.requests.append({"url": url, "params": params, "headers": headers or {}})
        return self.response


AUTO_CONFIG = {
    "token_endpoint": "https://auth.example.com/token",
    "token_method": "POST",
    "token_content_type": "json",
    "token_body": {"grant_type": "client_credentials", "client_id": "$secret.client_id"},
    "token_headers": {"X-Client": "demo"},
    "token_response_path": "data.access_token",
    "token_expires_in_path": "data.expires_in",
    "secrets": {"client_id": "cid", "client_secret": "sec"},
}


def test_normalize_token_strips_only_a_leading_bearer_prefix():
    assert mcp_auth.normalize_token("  Bearer abc.def ") == "abc.def"
    assert mcp_auth.normalize_token("bearer abc") == "abc"
    assert mcp_auth.normalize_token("BEARER\tabc") == "abc"
    assert mcp_auth.normalize_token("abc.def") == "abc.def"
    assert mcp_auth.normalize_token("Bearerish.abc") == "Bearerish.abc"  # 不误伤


def test_describe_token_expiry():
    moment = mcp_auth.describe_token_expiry(_jwt(3600))
    assert moment is not None and moment > datetime.now(timezone.utc)
    assert mcp_auth.describe_token_expiry(_jwt(None)) is None  # 没有 exp
    assert mcp_auth.describe_token_expiry("opaque-token") is None  # 非 JWT
    assert mcp_auth.describe_token_expiry("not.base64!.token") is None


def test_legacy_stored_token_with_prefix_is_sent_exactly_once():
    """P0 回归：存量数据里存了 'Bearer xxx'，出站只能是单层前缀。"""
    _, headers = asyncio.run(
        mcp_auth.prepare_mcp_endpoint(
            "https://api.example.com", "bearer", {"token": "Bearer eyJhbGc.abc.def"}
        )
    )
    assert headers["Authorization"] == "Bearer eyJhbGc.abc.def"


def test_expired_token_is_reported_as_a_config_error():
    token = _jwt(-60)
    with pytest.raises(AuthConfigError, match="已过期"):
        asyncio.run(
            mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", {"token": token})
        )


def test_saving_strips_the_pasted_prefix_and_header_line():
    assert mcp_auth.validate_auth_config("bearer", {"token": "Bearer abc.def"})["token"] == "abc.def"
    assert (
        mcp_auth.validate_auth_config(
            "api_key_header", {"header_name": "X-API-Key", "api_key": "X-API-Key: secret"}
        )["api_key"]
        == "secret"
    )
    assert mcp_auth.validate_auth_config("basic", {"username": " Basic alice", "password": "p"})[
        "username"
    ] == "alice"


def test_token_endpoint_https_policy_follows_the_private_network_switch():
    with pytest.raises(ValueError, match="HTTPS"):
        mcp_auth.validate_auth_config(
            "bearer", {"token_endpoint": "http://10.0.0.5/token"}, allow_private_network=False
        )
    accepted = mcp_auth.validate_auth_config(
        "bearer", {"token_endpoint": "http://10.0.0.5/token"}, allow_private_network=True
    )
    assert accepted["token_response_path"] == "access_token"  # 默认值已补上


def test_clearing_token_endpoint_switches_back_to_manual_token():
    result = mcp_auth.validate_auth_config("bearer", {"token": "abc", "token_endpoint": "  "})
    assert "token_endpoint" not in result
    assert result["token"] == "abc"


def test_bearer_auto_mode_uses_the_cached_token(monkeypatch):
    async def cached(key: str):
        return "cached-token"

    monkeypatch.setattr(mcp_auth.token_cache, "get_token", cached)
    client = _FakeTokenClient(_FakeResponse(200, {"data": {"access_token": "fresh"}}))
    monkeypatch.setattr(mcp_auth.httpx, "AsyncClient", client)

    _, headers = asyncio.run(
        mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", dict(AUTO_CONFIG))
    )
    assert headers["Authorization"] == "Bearer cached-token"
    assert client.requests == []  # 命中缓存就不该打 token 端点


def test_bearer_auto_mode_fetches_from_the_endpoint_and_caches_it(monkeypatch):
    stored: list[tuple[str, str, object]] = []

    async def missing(key: str):
        return None

    async def remember(key: str, token: str, expires_in):
        stored.append((key, token, expires_in))

    monkeypatch.setattr(mcp_auth.token_cache, "get_token", missing)
    monkeypatch.setattr(mcp_auth.token_cache, "store_token", remember)
    client = _FakeTokenClient(
        _FakeResponse(200, {"data": {"access_token": "fresh-token", "expires_in": 3600}})
    )
    monkeypatch.setattr(mcp_auth.httpx, "AsyncClient", client)

    _, headers = asyncio.run(
        mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", dict(AUTO_CONFIG))
    )

    assert headers["Authorization"] == "Bearer fresh-token"
    sent = client.requests[0]
    assert sent["url"] == "https://auth.example.com/token"
    assert sent["json"] == {"grant_type": "client_credentials", "client_id": "cid"}
    assert sent["headers"] == {"X-Client": "demo"}
    assert stored and stored[0][1] == "fresh-token" and stored[0][2] == 3600
    assert stored[0][0].startswith("capability:token:")


def test_bearer_auto_mode_rejects_unknown_secret_reference(monkeypatch):
    async def missing(key: str):
        return None

    async def remember(key: str, token: str, expires_in):
        return None

    monkeypatch.setattr(mcp_auth.token_cache, "get_token", missing)
    monkeypatch.setattr(mcp_auth.token_cache, "store_token", remember)
    client = _FakeTokenClient(_FakeResponse(200, {"data": {"access_token": "t"}}))
    monkeypatch.setattr(mcp_auth.httpx, "AsyncClient", client)

    config = dict(AUTO_CONFIG, token_body={"client_id": "$secret.nope"})
    with pytest.raises(AuthConfigError, match="unknown secret"):
        asyncio.run(
            mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", config)
        )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_FakeResponse(401, {}), AuthConfigError),
        (_FakeResponse(500, {}), AuthNegotiationError),
        (_FakeResponse(200, ValueError("bad json")), AuthNegotiationError),
        (_FakeResponse(200, {"data": {}}), AuthNegotiationError),
    ],
)
def test_token_endpoint_failures_are_classified(monkeypatch, response, expected):
    async def missing(key: str):
        return None

    async def remember(key: str, token: str, expires_in):
        return None

    monkeypatch.setattr(mcp_auth.token_cache, "get_token", missing)
    monkeypatch.setattr(mcp_auth.token_cache, "store_token", remember)
    monkeypatch.setattr(mcp_auth.httpx, "AsyncClient", _FakeTokenClient(response))

    with pytest.raises(expected):
        asyncio.run(
            mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", dict(AUTO_CONFIG))
        )


def test_token_endpoint_timeout_is_a_negotiation_error(monkeypatch):
    import httpx

    async def missing(key: str):
        return None

    monkeypatch.setattr(mcp_auth.token_cache, "get_token", missing)

    class _TimeoutClient(_FakeTokenClient):
        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(mcp_auth.httpx, "AsyncClient", _TimeoutClient(_FakeResponse(200, {})))

    with pytest.raises(AuthNegotiationError, match="timed out"):
        asyncio.run(
            mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", dict(AUTO_CONFIG))
        )


def test_missing_auth_field_is_a_config_error_not_a_keyerror():
    with pytest.raises(AuthConfigError, match="token"):
        asyncio.run(mcp_auth.prepare_mcp_endpoint("https://api.example.com", "bearer", {}))
    with pytest.raises(AuthConfigError, match="header_name"):
        asyncio.run(
            mcp_auth.prepare_mcp_endpoint(
                "https://api.example.com", "api_key_header", {"api_key": "k"}
            )
        )


def test_compute_ttl_keeps_a_safety_margin():
    assert token_cache.compute_ttl(3600) == 3570
    assert token_cache.compute_ttl(None) == token_cache.DEFAULT_TTL_SECONDS
    assert token_cache.compute_ttl("120") == 90
    assert token_cache.compute_ttl(20) is None  # 太短，不值得缓存


def test_token_cache_degrades_when_redis_is_unavailable(monkeypatch, caplog):
    def unavailable():
        raise RedisError("connection refused")

    monkeypatch.setattr(token_cache, "_client", unavailable)

    assert asyncio.run(token_cache.get_token("capability:token:x")) is None
    asyncio.run(token_cache.store_token("capability:token:x", "t", 3600))  # 不抛异常
    assert "Token 缓存不可用" in caplog.text


def test_secret_fingerprint_does_not_leak_the_secret():
    fingerprint = token_cache.secret_fingerprint({"client_secret": "super-secret"})
    assert "super-secret" not in fingerprint
    assert fingerprint == token_cache.secret_fingerprint({"client_secret": "super-secret"})
    assert fingerprint != token_cache.secret_fingerprint({"client_secret": "other"})


def test_token_endpoint_allows_loopback_http_without_the_private_switch():
    """回环地址上的 HTTP token 端点在改造前就可用，不能被新的策略收紧掉。"""
    config = mcp_auth.validate_auth_config(
        "bearer", {"token_endpoint": "http://localhost:9000/token"}
    )
    assert config["token_endpoint"] == "http://localhost:9000/token"


def test_summary_echoes_non_secret_fields_and_reports_secret_presence():
    summary = mcp_auth.summarize_auth_config(
        "api_key_header", {"header_name": "X-API-Key", "api_key": "super-secret"}
    )
    assert summary["header_name"] == "X-API-Key"
    assert summary["configured_secrets"] == ["api_key"]
    assert "super-secret" not in json.dumps(summary, ensure_ascii=False)


def test_summary_never_leaks_any_secret_across_auth_types():
    configs = {
        "bearer": {"token": "SECRET-TOKEN", "token_endpoint": "https://sso/token"},
        "api_key_query": {"parameter_name": "key", "api_key": "SECRET-QUERY-KEY"},
        "basic": {"username": "alice", "password": "SECRET-PASSWORD"},
        "oauth2_client_credentials": {
            "token_url": "https://sso/token",
            "client_id": "cid",
            "client_secret": "SECRET-CLIENT",
        },
        "custom_headers": {"headers": {"X-Tenant": "SECRET-HEADER"}},
        "custom_query_params": {"query_params": {"tenant": "SECRET-PARAM"}},
    }
    for auth_type, config in configs.items():
        dumped = json.dumps(
            mcp_auth.summarize_auth_config(auth_type, config), ensure_ascii=False
        )
        assert "SECRET" not in dumped, auth_type


def test_summary_reports_the_token_shape_needed_for_debugging():
    summary = mcp_auth.summarize_auth_config("bearer", {"token": "Bearer " + _jwt(3600)})
    hint = summary["token_hint"]
    assert hint["has_bearer_prefix"] is True
    assert hint["is_jwt"] is True
    assert hint["expires_at"] is not None
    assert hint["length"] > 0
    assert "token" not in summary  # 原值不回显


def test_service_model_summary_property_swallows_decrypt_failures(monkeypatch):
    from app import models

    service = models.ApiService(auth_type="bearer", auth_config_encrypted="ciphertext")
    monkeypatch.setattr(models, "decrypt_auth_config", lambda value: {"token": "SECRET"})
    assert service.auth_config_summary["configured_secrets"] == ["token"]

    def broken(value):
        raise ValueError("Stored MCP credentials cannot be decrypted")

    monkeypatch.setattr(models, "decrypt_auth_config", broken)
    assert "cannot be decrypted" in service.auth_config_summary["error"]

    service.auth_config_encrypted = None
    assert service.auth_config_summary == {}
