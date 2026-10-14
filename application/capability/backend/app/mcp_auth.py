import base64
import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .config import settings

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
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_FORBIDDEN_HEADERS = {"connection", "content-length", "host", "transfer-encoding"}


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


def validate_auth_config(auth_type: str, config: dict[str, Any]) -> dict[str, Any]:
    if auth_type not in AUTH_TYPES:
        raise ValueError(f"Unsupported MCP authentication type: {auth_type}")
    result = dict(config)
    if auth_type != "custom_query_params" and "query_params" in result:
        raise ValueError("query_params can only be used with custom_query_params authentication")
    allowed_config = {
        "none": set(),
        "bearer": {"token"},
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
        token = required("token")
        _validate_header("Authorization", f"Bearer {token}")
    elif auth_type == "api_key_header":
        required("api_key")
        result.setdefault("header_name", "X-API-Key")
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
        required("username")
        required("password")
    elif auth_type == "oauth2_client_credentials":
        token_url = required("token_url")
        parsed = urlsplit(token_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("token_url must be an absolute HTTP(S) URL")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("OAuth token_url must use HTTPS")
        if parsed.username or parsed.password or any(
            name.lower() in _SECRET_QUERY_NAMES for name, _ in parse_qsl(parsed.query)
        ):
            raise ValueError("OAuth token_url must not contain embedded credentials")
        required("client_id")
        required("client_secret")
        method = result.setdefault("client_auth_method", "client_secret_basic")
        if method not in {"client_secret_basic", "client_secret_post"}:
            raise ValueError("client_auth_method must be client_secret_basic or client_secret_post")

    return result


def _validate_header(name: Any, value: str) -> None:
    if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
        raise ValueError("Invalid HTTP header name")
    if name.lower() in _FORBIDDEN_HEADERS:
        raise ValueError(f"The {name} header cannot be overridden")
    if "\r" in value or "\n" in value:
        raise ValueError("HTTP header values cannot contain newlines")


async def _oauth_access_token(config: dict[str, Any]) -> str:
    data: dict[str, str] = {"grant_type": "client_credentials"}
    if config.get("scope"):
        data["scope"] = config["scope"]
    if config.get("audience"):
        data["audience"] = config["audience"]

    headers: dict[str, str] = {}
    if config.get("client_auth_method", "client_secret_basic") == "client_secret_basic":
        credentials = f"{quote_plus(config['client_id'])}:{quote_plus(config['client_secret'])}"
        authorization = base64.b64encode(credentials.encode("ascii")).decode("ascii")
        headers["Authorization"] = f"Basic {authorization}"
    else:
        data["client_id"] = config["client_id"]
        data["client_secret"] = config["client_secret"]

    async with httpx.AsyncClient(timeout=AUTH_REQUEST_TIMEOUT) as client:
        response = await client.post(config["token_url"], data=data, headers=headers)
    if not response.is_success:
        raise ValueError(f"OAuth token endpoint returned HTTP {response.status_code}")
    try:
        token = response.json().get("access_token")
    except (ValueError, AttributeError) as exc:
        raise ValueError("OAuth token endpoint returned invalid JSON") from exc
    if not isinstance(token, str) or not token:
        raise ValueError("OAuth token endpoint response has no access_token")
    return token


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
        headers["Authorization"] = f"Bearer {config['token']}"
    elif auth_type == "api_key_header":
        headers[config["header_name"]] = config["api_key"]
    elif auth_type == "api_key_query":
        set_query_params({config["parameter_name"]: config["api_key"]})
    elif auth_type == "custom_headers":
        headers.update(config["headers"])
    elif auth_type == "custom_query_params":
        set_query_params(config["query_params"])
    elif auth_type == "basic":
        raw = f"{config['username']}:{config['password']}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
    elif auth_type == "oauth2_client_credentials":
        token = await _oauth_access_token(config)
        headers["Authorization"] = f"Bearer {token}"
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
