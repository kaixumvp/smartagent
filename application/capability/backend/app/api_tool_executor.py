import asyncio
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .mcp_auth import decrypt_auth_config, prepare_mcp_endpoint
from .models import ApiService, Tool

MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BODY_BYTES = 1_048_576
MAX_MAPPING_BYTES = 16_384
MAX_PATH_BYTES = 8_192
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
    pass


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
        raise ApiToolCallError("API service resolves to a non-public address; enable private-network access only for trusted services")


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
                raise ApiToolCallError(f"Required Tool input '{path}' is missing")
            current = current[part]
    return current


def _render_path(path_template: str, arguments: dict[str, Any]) -> str:
    parsed = urlsplit(path_template)
    if not path_template.startswith("/") or path_template.startswith("//") or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ApiToolCallError("API Tool path must be a relative path starting with '/' and cannot include a query or host")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = arguments.get(key)
        if value is None or isinstance(value, (dict, list)):
            raise ApiToolCallError(f"Required path argument '{key}' is missing or is not scalar")
        return quote(str(value), safe="")

    rendered = _PATH_PARAMETER.sub(replace, path_template)
    if len(rendered.encode("utf-8")) > MAX_PATH_BYTES:
        raise ApiToolCallError("API Tool path exceeds the 8 KiB limit")
    return rendered


def _render_headers(template: dict[str, Any], arguments: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in template.items():
        if name.lower() in _FORBIDDEN_HEADERS or "\r" in name or "\n" in name:
            raise ApiToolCallError(f"Header '{name}' cannot be set by a Tool")
        resolved = _resolve_input_value(value, arguments)
        if resolved is None or isinstance(resolved, (dict, list)):
            raise ApiToolCallError(f"Header '{name}' must resolve to a scalar value")
        header_value = str(resolved)
        if "\r" in header_value or "\n" in header_value:
            raise ApiToolCallError(f"Header '{name}' contains invalid newline characters")
        headers[name] = header_value
    return headers


async def call_api_tool(service: ApiService, tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    if not service.enabled:
        raise ApiToolCallError("API service is disabled")
    if len(json.dumps(arguments, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise ApiToolCallError("API Tool arguments exceed the 1 MiB limit")
    validate_service_url(service.base_url, service.allow_private_network)
    base = urlsplit(service.base_url)
    await _validate_resolved_host(base.hostname or "", service.allow_private_network)

    execution = (tool.manifest or {}).get("execution") or {}
    if execution.get("kind") != "http":
        raise ApiToolCallError("API Tool has no valid HTTP execution configuration")
    method = execution.get("method")
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ApiToolCallError("API Tool has an unsupported HTTP method")
    path = _render_path(execution.get("path", ""), arguments)
    url = urljoin(service.base_url.rstrip("/") + "/", path.lstrip("/"))
    parsed_url = urlsplit(url)
    if (parsed_url.scheme, parsed_url.hostname, parsed_url.port) != (base.scheme, base.hostname, base.port):
        raise ApiToolCallError("API Tool path cannot change the configured service host")

    query = _resolve_input_value(execution.get("query_template") or {}, arguments)
    if not isinstance(query, dict):
        raise ApiToolCallError("API Tool query template must be an object")
    if any(isinstance(value, (dict, list)) for value in query.values()):
        raise ApiToolCallError("API Tool query values must resolve to scalars")
    if len(json.dumps(query, ensure_ascii=False).encode("utf-8")) > MAX_MAPPING_BYTES:
        raise ApiToolCallError("API Tool query mapping exceeds the 16 KiB limit")
    headers = _render_headers(execution.get("header_template") or {}, arguments)
    if len(json.dumps(headers, ensure_ascii=False).encode("utf-8")) > MAX_MAPPING_BYTES:
        raise ApiToolCallError("API Tool headers exceed the 16 KiB limit")
    body_template = execution.get("body_template")
    body = _resolve_input_value(body_template, arguments) if body_template is not None else None
    if body is not None and len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise ApiToolCallError("API request body exceeds the 1 MiB limit")
    auth_config = decrypt_auth_config(service.auth_config_encrypted)
    if service.auth_type == "oauth2_client_credentials":
        token_url = auth_config.get("token_url", "")
        validate_service_url(token_url, service.allow_private_network)
        await _validate_resolved_host(
            urlsplit(token_url).hostname or "", service.allow_private_network
        )
    request_url, auth_headers = await prepare_mcp_endpoint(
        url, service.auth_type, auth_config
    )
    headers.update(auth_headers)

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
                if not response.is_success:
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
                return {
                    "isError": False,
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": result,
                    "statusCode": response.status_code,
                }
    except httpx.TimeoutException as exc:
        raise ApiToolCallError("API request timed out") from exc
    except httpx.RequestError as exc:
        raise ApiToolCallError(f"API request failed ({type(exc).__name__})") from exc
