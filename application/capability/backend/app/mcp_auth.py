import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from . import token_cache
from .config import settings

logger = logging.getLogger(__name__)

AUTH_TYPES = {
    "none",
    "bearer",
    "api_key_header",
    "api_key_query",
    "custom_headers",
    "custom_query_params",
    "basic",
    "oauth2_client_credentials",
}

AUTH_REQUEST_TIMEOUT = 30
# 手工 token 临近过期就提前报错，避免拿着马上失效的凭据去调远端
TOKEN_EXPIRY_WARNING_SECONDS = 60
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_FORBIDDEN_HEADERS = {"connection", "content-length", "host", "transfer-encoding"}
_BEARER_PREFIX = re.compile(r"^\s*bearer\s+", re.IGNORECASE)
_BASIC_PREFIX = re.compile(r"^\s*basic\s+", re.IGNORECASE)


class AuthConfigError(ValueError):
    """存储的认证配置缺失或不可用，需要重新保存凭据（router 映射 422）。"""


class AuthNegotiationError(RuntimeError):
    """换取访问令牌时的网络/远端失败，不是本地配置问题（router 映射 502）。"""

    status_code = 502


def _fernet() -> Fernet:
    key = settings.mcp_auth_encryption_key
    if not key:
        raise ValueError("MCP_AUTH_ENCRYPTION_KEY must be configured before saving credentials")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("MCP_AUTH_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_auth_config(config: dict[str, Any]) -> str | None:
    if not config:
        return None
    payload = json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_auth_config(encrypted: str | None) -> dict[str, Any]:
    if not encrypted:
        return {}
    try:
        payload = _fernet().decrypt(encrypted.encode("ascii"))
        result = json.loads(payload)
    except (InvalidToken, UnicodeEncodeError, json.JSONDecodeError) as exc:
        raise ValueError("Stored MCP credentials cannot be decrypted; check MCP_AUTH_ENCRYPTION_KEY") from exc
    if not isinstance(result, dict):
        raise ValueError("Stored MCP authentication configuration is invalid")
    return result


_SECRET_REFERENCE = re.compile(r"^\$secret(?:\.([A-Za-z_][A-Za-z0-9_.]*))?$")


def normalize_token(value: str) -> str:
    """去掉首尾空白，以及用户从接口文档里连前缀一起粘进来的 `Bearer `。

    只剥离 token 开头的 `Bearer `：真实 token 不会以它开头，而它是只读文档里最常见的复制形态。
    """
    return _BEARER_PREFIX.sub("", str(value).strip(), count=1).strip()


def describe_token_expiry(token: str) -> datetime | None:
    """解析 JWT payload 里的 `exp`（不验签，仅用于提示）。非 JWT 或解析失败返回 None。"""
    parts = normalize_token(token).split(".")
    if len(parts) != 3:
        return None
    segment = parts[1]
    try:
        payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        expires_at = payload.get("exp")
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(expires_at), timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def ensure_token_usable(token: str) -> None:
    """手工 token 已过期或即将过期时直接报明确错误，而不是让远端返回 401/403 再被笼统报成 502。"""
    expires_at = describe_token_expiry(token)
    if expires_at is None:
        return
    remaining = expires_at - datetime.now(timezone.utc)
    if remaining <= timedelta(seconds=TOKEN_EXPIRY_WARNING_SECONDS):
        state = "已过期" if remaining.total_seconds() <= 0 else "即将过期"
        raise AuthConfigError(
            f"Bearer token {state}（{expires_at.isoformat()}），请在 API 服务里更新凭据"
        )


def _required(config: dict[str, Any], name: str) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AuthConfigError(
            f"Authentication field '{name}' is missing; re-save the API service credentials"
        )
    return value.strip()


def _resolve_secret_refs(value: Any, secrets: dict[str, Any]) -> Any:
    """把取 token 请求模板里的 `$secret.xxx` 替换成 secrets 里的值。"""
    if isinstance(value, dict):
        return {key: _resolve_secret_refs(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_secret_refs(item, secrets) for item in value]
    if not isinstance(value, str):
        return value
    match = _SECRET_REFERENCE.fullmatch(value.strip())
    if match is None:
        return value
    path = match.group(1)
    current: Any = secrets
    if path:
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise AuthConfigError(f"Token request references unknown secret '{path}'")
            current = current[part]
    return current


def _json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


async def _request_token(
    url: str,
    *,
    method: str = "POST",
    content_type: str = "form",
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """向 token 端点取令牌，并把失败按“配置错 / 远端错”分类（不再一律算 503）。"""
    try:
        async with httpx.AsyncClient(
            timeout=AUTH_REQUEST_TIMEOUT, follow_redirects=False, trust_env=False
        ) as client:
            if method == "GET":
                response = await client.get(url, params=data, headers=headers)
            elif content_type == "json":
                response = await client.post(url, json=data, headers=headers)
            else:
                response = await client.post(url, data=data, headers=headers)
    except httpx.TimeoutException as exc:
        raise AuthNegotiationError("Token endpoint timed out") from exc
    except httpx.RequestError as exc:
        raise AuthNegotiationError(
            f"Token endpoint request failed ({type(exc).__name__})"
        ) from exc

    if response.status_code in {400, 401, 403}:
        raise AuthConfigError(
            f"Token endpoint rejected the credentials (HTTP {response.status_code}); "
            "re-save the API service credentials"
        )
    if not response.is_success:
        raise AuthNegotiationError(f"Token endpoint returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise AuthNegotiationError("Token endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AuthNegotiationError("Token endpoint response must be a JSON object")
    return payload


async def _cached_or_fetch(key: str, fetch: Any) -> str:
    """先查缓存，未命中再取并写回；缓存设施故障只记日志，绝不影响调用。"""
    cached = await token_cache.get_token(key)
    if cached:
        return cached
    token, expires_in = await fetch()
    await token_cache.store_token(key, token, expires_in)
    return token


async def _bearer_access_token(config: dict[str, Any]) -> str:
    """bearer 的 token 来源：手工填写，或用请求模板从 token 端点自动获取（带 Redis 缓存）。"""
    endpoint = config.get("token_endpoint")
    if not endpoint:
        token = normalize_token(_required(config, "token"))
        ensure_token_usable(token)
        return token

    method = str(config.get("token_method") or "POST").upper()
    content_type = str(config.get("token_content_type") or "form")
    response_path = str(config.get("token_response_path") or "access_token")
    expires_in_path = str(config.get("token_expires_in_path") or "expires_in")
    secrets = config.get("secrets") or {}
    key = token_cache.cache_key(
        {
            "kind": "token-request",
            "endpoint": endpoint,
            "method": method,
            "content_type": content_type,
            "body": config.get("token_body") or {},
            "headers": config.get("token_headers") or {},
            "response_path": response_path,
            "secrets": token_cache.secret_fingerprint(secrets),
        }
    )

    async def fetch() -> tuple[str, Any]:
        raw_headers = _resolve_secret_refs(config.get("token_headers") or {}, secrets)
        payload = await _request_token(
            endpoint,
            method=method,
            content_type=content_type,
            data=_resolve_secret_refs(config.get("token_body") or {}, secrets),
            headers={str(name): str(value) for name, value in raw_headers.items()},
        )
        token = _json_path(payload, response_path)
        if not isinstance(token, str) or not token:
            raise AuthNegotiationError(f"Token endpoint response has no '{response_path}'")
        return normalize_token(token), _json_path(payload, expires_in_path)

    return await _cached_or_fetch(key, fetch)


def _token_hint(token: str) -> dict[str, Any]:
    """只给排查用的形态信息（长度/是否带前缀/是否 JWT/到期时间），不含 token 本身。"""
    raw = str(token)
    expires_at = describe_token_expiry(raw)
    return {
        "length": len(raw.strip()),
        "has_bearer_prefix": bool(_BEARER_PREFIX.match(raw)),
        "is_jwt": raw.strip().count(".") == 2,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


# 可以原样回显的字段（不含任何密钥），编辑表单用它预填
_PUBLIC_AUTH_FIELDS = (
    "header_name",
    "parameter_name",
    "username",
    "token_url",
    "client_id",
    "scope",
    "audience",
    "client_auth_method",
    "token_endpoint",
    "token_method",
    "token_content_type",
    "token_body",
    "token_headers",
    "token_response_path",
    "token_expires_in_path",
)
_SECRET_AUTH_FIELDS = ("token", "api_key", "password", "client_secret")


def summarize_auth_config(auth_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """认证配置回显：非敏感字段原样给出，密钥只给“是否已配置”和形态诊断。

    管理 API 无用户鉴权且 CORS 为 *，因此 token / api_key / password / client_secret /
    自定义 header 与 query 的值、secrets 的值一律不回显——只回名字或形态信息。
    """
    summary: dict[str, Any] = {"auth_type": auth_type}
    for name in _PUBLIC_AUTH_FIELDS:
        value = config.get(name)
        if value not in (None, "", {}, []):
            summary[name] = value
    for name in ("headers", "query_params", "secrets"):
        value = config.get(name)
        if isinstance(value, dict) and value:
            summary[name] = {key: "<redacted>" for key in value}
    configured = [name for name in _SECRET_AUTH_FIELDS if config.get(name)]
    if isinstance(config.get("secrets"), dict) and config["secrets"]:
        configured.append("secrets")
    summary["configured_secrets"] = configured
    if config.get("token"):
        summary["token_hint"] = _token_hint(config["token"])
    return summary


def validate_auth_config(
    auth_type: str,
    config: dict[str, Any],
    allow_private_network: bool = False,
) -> dict[str, Any]:
    if auth_type not in AUTH_TYPES:
        raise ValueError(f"Unsupported MCP authentication type: {auth_type}")
    result = dict(config)
    if auth_type != "custom_query_params" and "query_params" in result:
        raise ValueError("query_params can only be used with custom_query_params authentication")
    allowed_config = {
        "none": set(),
        "bearer": {
            # 手工 token
            "token",
            # 或者：用请求模板从 token 端点自动获取（结果缓存在 Redis）
            "token_endpoint",
            "token_method",
            "token_content_type",
            "token_body",
            "token_headers",
            "token_response_path",
            "token_expires_in_path",
            "secrets",
        },
        "api_key_header": {"header_name", "api_key"},
        "api_key_query": {"parameter_name", "api_key"},
        "custom_headers": {"headers"},
        "custom_query_params": {"query_params"},
        "basic": {"username", "password"},
        "oauth2_client_credentials": {
            "token_url",
            "client_id",
            "client_secret",
            "scope",
            "audience",
            "client_auth_method",
        },
    }
    unexpected = set(result) - allowed_config.get(auth_type, set())
    if unexpected:
        raise ValueError(f"Unexpected {auth_type} authentication field: {sorted(unexpected)[0]}")

    def required(name: str) -> str:
        value = result.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required for {auth_type}")
        result[name] = value.strip()
        return result[name]

    if auth_type == "none":
        if result:
            raise ValueError("Authentication settings must be empty when auth type is none")
    elif auth_type == "bearer":
        endpoint = result.get("token_endpoint")
        if isinstance(endpoint, str) and not endpoint.strip():
            # 传空串表示“改回手工 token”，清掉遗留的自动获取配置
            result.pop("token_endpoint", None)
            endpoint = None
        if endpoint:
            result.pop("token", None)
            _validate_token_source(result, allow_private_network)
        else:
            token = normalize_token(required("token"))
            result["token"] = token
            _validate_header("Authorization", f"Bearer {token}")
    elif auth_type == "api_key_header":
        required("api_key")
        result.setdefault("header_name", "X-API-Key")
        # 允许直接粘 "X-API-Key: xxx" 这种整行写法
        prefix = f"{result['header_name']}:"
        if result["api_key"].lower().startswith(prefix.lower()):
            result["api_key"] = result["api_key"][len(prefix):].strip()
        _validate_header(result["header_name"], result["api_key"])
    elif auth_type == "api_key_query":
        required("api_key")
        result.setdefault("parameter_name", "key")
        required("parameter_name")
    elif auth_type == "custom_headers":
        headers = result.get("headers")
        if not isinstance(headers, dict) or not headers:
            raise ValueError("At least one custom HTTP header is required")
        for name, value in headers.items():
            if not isinstance(value, str):
                raise ValueError("Custom HTTP header values must be strings")
            _validate_header(name, value)
    elif auth_type == "custom_query_params":
        params = result.get("query_params")
        if not isinstance(params, dict) or not params:
            raise ValueError("At least one custom query parameter is required")
        if any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in params.items()):
            raise ValueError("Query parameter names and values must be non-empty strings")
    elif auth_type == "basic":
        username = required("username")
        if _BASIC_PREFIX.match(username):
            username = _BASIC_PREFIX.sub("", username, count=1).strip()
            if not username:
                raise ValueError("username is required for basic")
            result["username"] = username
        required("password")
    elif auth_type == "oauth2_client_credentials":
        _validate_token_url(required("token_url"), allow_private_network)
        required("client_id")
        required("client_secret")
        method = result.setdefault("client_auth_method", "client_secret_basic")
        if method not in {"client_secret_basic", "client_secret_post"}:
            raise ValueError("client_auth_method must be client_secret_basic or client_secret_post")

    return result


def _validate_token_url(token_url: str, allow_private_network: bool) -> str:
    """token 端点 URL：形状必须合法；是否允许明文 HTTP 由服务的私网开关决定。"""
    parsed = urlsplit(token_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Token URL must be an absolute HTTP(S) URL")
    if (
        parsed.scheme != "https"
        and not allow_private_network
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Token URL must use HTTPS unless private-network access is enabled")
    if parsed.username or parsed.password or any(
        name.lower() in _SECRET_QUERY_NAMES for name, _ in parse_qsl(parsed.query)
    ):
        raise ValueError("Token URL must not contain embedded credentials")
    return token_url


def _validate_token_source(config: dict[str, Any], allow_private_network: bool) -> None:
    """校验 bearer 的“自动获取 token”配置（请求模板 + secrets）。"""
    _validate_token_url(_required(config, "token_endpoint"), allow_private_network)
    method = str(config.get("token_method") or "POST").upper()
    if method not in {"GET", "POST"}:
        raise ValueError("token_method must be GET or POST")
    config["token_method"] = method
    content_type = str(config.get("token_content_type") or "form")
    if content_type not in {"json", "form"}:
        raise ValueError("token_content_type must be json or form")
    config["token_content_type"] = content_type
    if not isinstance(config.get("token_body") or {}, dict):
        raise ValueError("token_body must be a JSON object")
    headers = config.get("token_headers") or {}
    if not isinstance(headers, dict) or any(
        not isinstance(value, (str, int, float)) for value in headers.values()
    ):
        raise ValueError("token_headers must be a JSON object of scalar values")
    secrets = config.get("secrets") or {}
    if not isinstance(secrets, dict) or any(
        not isinstance(value, (str, int, float)) for value in secrets.values()
    ):
        raise ValueError("secrets must be a JSON object of scalar values")
    config.setdefault("token_response_path", "access_token")
    config.setdefault("token_expires_in_path", "expires_in")


def _validate_header(name: Any, value: str) -> None:
    if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
        raise ValueError("Invalid HTTP header name")
    if name.lower() in _FORBIDDEN_HEADERS:
        raise ValueError(f"The {name} header cannot be overridden")
    if "\r" in value or "\n" in value:
        raise ValueError("HTTP header values cannot contain newlines")


async def _oauth_access_token(config: dict[str, Any]) -> str:
    """标准 OAuth 2.0 client_credentials；token 走同一套 Redis 缓存。"""
    client_auth_method = config.get("client_auth_method", "client_secret_basic")
    key = token_cache.cache_key(
        {
            "kind": "oauth2",
            "token_url": config.get("token_url") or "",
            "client_id": config.get("client_id") or "",
            "scope": config.get("scope") or "",
            "audience": config.get("audience") or "",
            "client_auth_method": client_auth_method,
            "secret": token_cache.secret_fingerprint(
                {"client_secret": config.get("client_secret") or ""}
            ),
        }
    )

    async def fetch() -> tuple[str, Any]:
        data: dict[str, str] = {"grant_type": "client_credentials"}
        if config.get("scope"):
            data["scope"] = config["scope"]
        if config.get("audience"):
            data["audience"] = config["audience"]

        headers: dict[str, str] = {}
        client_id = _required(config, "client_id")
        client_secret = _required(config, "client_secret")
        if client_auth_method == "client_secret_basic":
            credentials = f"{quote_plus(client_id)}:{quote_plus(client_secret)}"
            authorization = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {authorization}"
        else:
            data["client_id"] = client_id
            data["client_secret"] = client_secret

        payload = await _request_token(
            _required(config, "token_url"),
            method="POST",
            content_type="form",
            data=data,
            headers=headers,
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AuthNegotiationError("Token endpoint response has no access_token")
        return normalize_token(token), payload.get("expires_in")

    return await _cached_or_fetch(key, fetch)


def _required_mapping(config: dict[str, Any], name: str) -> dict[str, str]:
    value = config.get(name)
    if not isinstance(value, dict) or not value:
        raise AuthConfigError(
            f"Authentication field '{name}' is missing; re-save the API service credentials"
        )
    return {str(key): str(item) for key, item in value.items()}


async def prepare_mcp_endpoint(
    endpoint: str,
    auth_type: str,
    config: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    headers: dict[str, str] = {}
    parsed = urlsplit(endpoint)
    query = parse_qsl(parsed.query, keep_blank_values=True)

    def set_query_params(params: dict[str, str]) -> None:
        names = set(params)
        query[:] = [(name, value) for name, value in query if name not in names]
        query.extend(params.items())

    if auth_type == "none":
        pass
    elif auth_type == "bearer":
        headers["Authorization"] = f"Bearer {await _bearer_access_token(config)}"
    elif auth_type == "api_key_header":
        headers[_required(config, "header_name")] = _required(config, "api_key")
    elif auth_type == "api_key_query":
        set_query_params({_required(config, "parameter_name"): _required(config, "api_key")})
    elif auth_type == "custom_headers":
        headers.update(_required_mapping(config, "headers"))
    elif auth_type == "custom_query_params":
        set_query_params(_required_mapping(config, "query_params"))
    elif auth_type == "basic":
        credentials = f"{_required(config, 'username')}:{_required(config, 'password')}"
        headers["Authorization"] = f"Basic {base64.b64encode(credentials.encode('utf-8')).decode('ascii')}"
    elif auth_type == "oauth2_client_credentials":
        headers["Authorization"] = f"Bearer {await _oauth_access_token(config)}"
    else:
        raise ValueError(f"Unsupported MCP authentication type: {auth_type}")

    prepared_endpoint = urlunsplit(parsed._replace(query=urlencode(query)))
    return prepared_endpoint, headers


def reject_secret_query_params(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password:
        raise ValueError("Provider endpoint must not contain embedded credentials")
    if any(name.lower() in _SECRET_QUERY_NAMES for name, _ in parse_qsl(parsed.query)):
        raise ValueError("Put query-string credentials in the Provider authentication settings")


_SECRET_QUERY_NAMES = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "token",
}
