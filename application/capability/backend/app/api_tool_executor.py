import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .config import settings
from .mcp_auth import (
    AuthConfigError,
    AuthNegotiationError,
    decrypt_auth_config,
    describe_token_expiry,
    prepare_mcp_endpoint,
)
from .models import ApiService, Tool

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BODY_BYTES = 1_048_576
MAX_MAPPING_BYTES = 16_384
MAX_PATH_BYTES = 8_192
# 出站日志里 body / 响应预览的最大字符数，避免日志被大响应刷爆
MAX_LOG_BODY_CHARS = 2_000
MAX_LOG_BODY_BYTES = 8_192
_PATH_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_INPUT_REFERENCE = re.compile(r"^\$input(?:\.([A-Za-z_][A-Za-z0-9_.]*))?$")
_FORBIDDEN_HEADERS = {
    "authorization",
    "connection",
    "content-length",
    "cookie",
    "host",
    "keep-alive",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class ApiToolCallError(RuntimeError):
    """API Tool 执行失败的基类，默认 502：问题出在远端服务或网络。

    分类规则：错误由调用方传入的参数引起 → ApiToolRequestError(400)；
    由 Tool / Service 的存储定义不可用引起 → ApiToolConfigError(422)；
    由网络策略拒绝引起 → ApiToolBlockedError(403)；
    其余（远端非 2xx、连接失败、响应超限）保留 502；超时为 504。
    Router 直接使用 exc.status_code，不再靠字符串匹配判断。
    """

    status_code = 502


class ApiToolRequestError(ApiToolCallError):
    """调用方入参不满足 Tool 契约（缺参、类型不对、超出限额）。"""

    status_code = 400


class ApiToolConfigError(ApiToolCallError):
    """Tool / Service 的存储定义拼不出合法请求，属配置问题。"""

    status_code = 422


class ApiToolBlockedError(ApiToolCallError):
    """目标地址被网络策略拒绝，例如解析到非公网地址。"""

    status_code = 403


class ApiToolTimeoutError(ApiToolCallError):
    """请求超时。"""

    status_code = 504


# 出站日志里按名称脱敏的 header / query 参数（子串匹配，忽略大小写）。
# 覆盖 Authorization、Cookie、X-API-Key、token/secret/password 这类常见命名，
# 以及 api_key_query 认证方式把密钥放进 query 的情况。
_SENSITIVE_NAME_PARTS = (
    "authorization",
    "cookie",
    "key",
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "sign",
    "auth",
    "credential",
    "session",
)
_REDACTED = "<redacted>"


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in _SENSITIVE_NAME_PARTS)


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if not _is_sensitive_name(name):
            redacted[name] = value
            continue
        # 保留 "Bearer" / "Basic" 这类方案名，值本身一律替换
        scheme, _, remainder = value.partition(" ")
        redacted[name] = f"{scheme} {_REDACTED}" if remainder else _REDACTED
    return redacted


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.query:
        return url
    redacted_query = urlencode(
        [
            (name, _REDACTED if _is_sensitive_name(name) else value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        ],
        safe="<>",
    )
    return urlunsplit(parsed._replace(query=redacted_query))


def _redact_query_values(query: dict[str, Any]) -> dict[str, Any]:
    """api_key_query 认证会把密钥放进 query，单独打印 query 时同样要脱敏。"""
    return {
        name: (_REDACTED if _is_sensitive_name(name) else value)
        for name, value in query.items()
    }


def _preview(value: Any) -> str:
    if value is None:
        return "<无>"
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_LOG_BODY_CHARS:
        return f"{text[:MAX_LOG_BODY_CHARS]}…（共 {len(text)} 字符，已截断）"
    return text


async def _read_body_preview(response: httpx.Response) -> str:
    """读取（最多 MAX_LOG_BODY_BYTES 字节）响应体用于日志，读取失败不影响结果。"""
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_LOG_BODY_BYTES:
                break
    except httpx.HTTPError as exc:
        return f"<读取响应体失败：{type(exc).__name__}>"
    text = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    if len(text) > MAX_LOG_BODY_CHARS:
        return f"{text[:MAX_LOG_BODY_CHARS]}…（已截断）"
    return text


def _log_prefix(tool: Tool) -> str:
    # 用 getattr：日志绝不能因为取不到名字而打断真实调用
    name = getattr(tool, "display_name", None) or getattr(tool, "name", None)
    identifier = getattr(tool, "id", None)
    return f"[{name or 'unknown'}{f' {identifier}' if identifier else ''}]"


def _token_validity_note(headers: dict[str, str]) -> str:
    """日志里提示 Bearer token 的剩余有效期（只输出时长，不打印 token）。"""
    authorization = next(
        (value for name, value in headers.items() if name.lower() == "authorization"), ""
    )
    if not authorization.lower().startswith("bearer "):
        return ""
    expires_at = describe_token_expiry(authorization.split(" ", 1)[1])
    if expires_at is None:
        return ""
    remaining = expires_at - datetime.now(timezone.utc)
    return f"token 剩余有效期 {remaining}（到期 {expires_at.isoformat()}）"


def _display_url(request_url: str, query: dict[str, Any]) -> str:
    if not query:
        return request_url
    try:
        return str(httpx.URL(request_url, params=query))
    except (httpx.InvalidURL, TypeError):
        return request_url


def validate_service_url(base_url: str, allow_private_network: bool) -> None:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Base URL must be an HTTP(S) origin/path without credentials, query, or fragment")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Base URL contains an invalid port") from exc
    if parsed.scheme != "https" and not allow_private_network:
        raise ValueError("HTTPS is required unless private-network access is explicitly enabled")


async def _validate_resolved_host(hostname: str, allow_private_network: bool) -> None:
    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            records = await asyncio.to_thread(
                socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise ApiToolCallError("API service host could not be resolved") from exc
        addresses = {ipaddress.ip_address(record[4][0]) for record in records}
    else:
        addresses = {literal_address}

    if not addresses:
        raise ApiToolCallError("API service host resolved to no addresses")
    if not allow_private_network and any(not address.is_global for address in addresses):
        raise ApiToolBlockedError("API service resolves to a non-public address; enable private-network access only for trusted services")


def _resolve_input_value(value: Any, arguments: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        if isinstance(value, dict):
            return {key: _resolve_input_value(item, arguments) for key, item in value.items()}
        if isinstance(value, list):
            return [_resolve_input_value(item, arguments) for item in value]
        return value

    match = _INPUT_REFERENCE.fullmatch(value)
    if match is None:
        return value
    path = match.group(1)
    current: Any = arguments
    if path:
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ApiToolRequestError(f"Required Tool input '{path}' is missing")
            current = current[part]
    return current


def _render_path(path_template: str, arguments: dict[str, Any]) -> str:
    parsed = urlsplit(path_template)
    if not path_template.startswith("/") or path_template.startswith("//") or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ApiToolConfigError("API Tool path must be a relative path starting with '/' and cannot include a query or host")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = arguments.get(key)
        if value is None or isinstance(value, (dict, list)):
            raise ApiToolRequestError(f"Required path argument '{key}' is missing or is not scalar")
        return quote(str(value), safe="")

    rendered = _PATH_PARAMETER.sub(replace, path_template)
    if len(rendered.encode("utf-8")) > MAX_PATH_BYTES:
        raise ApiToolRequestError("API Tool path exceeds the 8 KiB limit")
    return rendered


def _render_headers(template: dict[str, Any], arguments: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in template.items():
        if name.lower() in _FORBIDDEN_HEADERS or "\r" in name or "\n" in name:
            raise ApiToolConfigError(f"Header '{name}' cannot be set by a Tool")
        resolved = _resolve_input_value(value, arguments)
        if resolved is None or isinstance(resolved, (dict, list)):
            raise ApiToolRequestError(f"Header '{name}' must resolve to a scalar value")
        header_value = str(resolved)
        if "\r" in header_value or "\n" in header_value:
            raise ApiToolRequestError(f"Header '{name}' contains invalid newline characters")
        headers[name] = header_value
    return headers


async def call_api_tool(service: ApiService, tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    if not service.enabled:
        raise ApiToolConfigError("API service is disabled")
    if len(json.dumps(arguments, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise ApiToolRequestError("API Tool arguments exceed the 1 MiB limit")
    validate_service_url(service.base_url, service.allow_private_network)
    base = urlsplit(service.base_url)
    await _validate_resolved_host(base.hostname or "", service.allow_private_network)

    execution = (tool.manifest or {}).get("execution") or {}
    if execution.get("kind") != "http":
        raise ApiToolConfigError("API Tool has no valid HTTP execution configuration")
    method = execution.get("method")
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ApiToolConfigError("API Tool has an unsupported HTTP method")
    path = _render_path(execution.get("path", ""), arguments)
    url = urljoin(service.base_url.rstrip("/") + "/", path.lstrip("/"))
    parsed_url = urlsplit(url)
    if (parsed_url.scheme, parsed_url.hostname, parsed_url.port) != (base.scheme, base.hostname, base.port):
        raise ApiToolConfigError("API Tool path cannot change the configured service host")

    query = _resolve_input_value(execution.get("query_template") or {}, arguments)
    if not isinstance(query, dict):
        raise ApiToolConfigError("API Tool query template must be an object")
    if any(isinstance(value, (dict, list)) for value in query.values()):
        raise ApiToolRequestError("API Tool query values must resolve to scalars")
    if len(json.dumps(query, ensure_ascii=False).encode("utf-8")) > MAX_MAPPING_BYTES:
        raise ApiToolRequestError("API Tool query mapping exceeds the 16 KiB limit")
    headers = _render_headers(execution.get("header_template") or {}, arguments)
    if len(json.dumps(headers, ensure_ascii=False).encode("utf-8")) > MAX_MAPPING_BYTES:
        raise ApiToolRequestError("API Tool headers exceed the 16 KiB limit")
    body_template = execution.get("body_template")
    body = _resolve_input_value(body_template, arguments) if body_template is not None else None
    if body is not None and len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise ApiToolRequestError("API request body exceeds the 1 MiB limit")
    auth_config = decrypt_auth_config(service.auth_config_encrypted)
    # 取令牌的地址也受网络策略约束，不能只校验业务 Base URL
    token_endpoint = auth_config.get(
        "token_endpoint" if service.auth_type == "bearer" else "token_url"
    ) if service.auth_type in {"bearer", "oauth2_client_credentials"} else None
    if token_endpoint:
        validate_service_url(token_endpoint, service.allow_private_network)
        await _validate_resolved_host(
            urlsplit(token_endpoint).hostname or "", service.allow_private_network
        )
    try:
        request_url, auth_headers = await prepare_mcp_endpoint(
            url, service.auth_type, auth_config
        )
    except AuthConfigError as exc:
        # 凭据缺失/过期属配置问题（422），不再冒成 500 或笼统的 502
        raise ApiToolConfigError(str(exc)) from exc
    except AuthNegotiationError as exc:
        # 取令牌时的网络/远端失败
        raise ApiToolCallError(str(exc)) from exc
    headers.update(auth_headers)

    # 出站日志：URL / header / body 全量打印，凭据按名称脱敏
    log_http = settings.api_tool_http_log
    display_url = _display_url(request_url, query)
    prefix = _log_prefix(tool)
    started = time.perf_counter()
    if log_http:
        validity = _token_validity_note(headers)
        logger.info(
            "API Tool 出站请求 %s %s %s\n  headers: %s\n  body: %s\n  query: %s"
            "\n  timeout: %ss · follow_redirects=False · trust_env=False%s",
            prefix,
            method,
            _redact_url(display_url),
            _redact_headers(headers),
            _preview(body),
            _preview(_redact_query_values(query)),
            service.request_timeout_seconds,
            f"\n  {validity}" if validity else "",
        )

    try:
        async with httpx.AsyncClient(
            timeout=service.request_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                method,
                request_url,
                params=query,
                headers=headers,
                json=body if body is not None else None,
            ) as response:
                elapsed_ms = (time.perf_counter() - started) * 1_000
                if not response.is_success:
                    if log_http:
                        hint = (
                            "\n  提示：401/403 多为凭据问题——token 是否重复带了 'Bearer ' 前缀、"
                            "是否已过期、scope 是否覆盖该接口"
                            if response.status_code in {401, 403}
                            else ""
                        )
                        logger.warning(
                            "API Tool 出站响应 %s HTTP %s（非 2xx，%.0fms）\n"
                            "  headers: %s\n  body: %s%s",
                            prefix,
                            response.status_code,
                            elapsed_ms,
                            _redact_headers(dict(response.headers)),
                            await _read_body_preview(response),
                            hint,
                        )
                    raise ApiToolCallError(f"API service returned HTTP {response.status_code}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ApiToolCallError("API response exceeds the 1 MiB limit")
                    chunks.append(chunk)
                raw_body = b"".join(chunks)
                try:
                    result: Any = json.loads(raw_body) if raw_body else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    result = raw_body.decode(response.encoding or "utf-8", errors="replace")
                text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                if log_http:
                    logger.info(
                        "API Tool 出站响应 %s HTTP %s（%.0fms · %d 字节）\n"
                        "  headers: %s\n  body: %s",
                        prefix,
                        response.status_code,
                        (time.perf_counter() - started) * 1_000,
                        len(raw_body),
                        _redact_headers(dict(response.headers)),
                        _preview(result),
                    )
                return {
                    "isError": False,
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": result,
                    "statusCode": response.status_code,
                }
    except httpx.TimeoutException as exc:
        if log_http:
            logger.warning(
                "API Tool 请求超时 %s %s %s（%ss）",
                prefix,
                method,
                _redact_url(display_url),
                service.request_timeout_seconds,
            )
        raise ApiToolTimeoutError("API request timed out") from exc
    except httpx.RequestError as exc:
        if log_http:
            logger.warning(
                "API Tool 请求失败 %s %s %s · %s: %s",
                prefix,
                method,
                _redact_url(display_url),
                type(exc).__name__,
                exc,
            )
        raise ApiToolCallError(f"API request failed ({type(exc).__name__})") from exc
