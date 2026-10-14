import asyncio
import re
from typing import Any, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .mcp_auth import prepare_mcp_endpoint

# 连接 + list_tools 的整体超时（秒）
SYNC_TIMEOUT = 30
_URL_QUERY = re.compile(r"""(https?://[^\s?'"<>]+)\?[^\s'"<>]+""")


def describe_mcp_error(exc: Exception) -> str:
    """Describe nested transport failures without exposing endpoint query secrets."""
    if isinstance(exc, ExceptionGroup):
        details = [describe_mcp_error(child) for child in exc.exceptions]
        return "; ".join(dict.fromkeys(details))
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        return f"远端 MCP 返回 HTTP {response.status_code} {response.reason_phrase}"
    if isinstance(exc, httpx.TimeoutException):
        return "远端 MCP 请求超时"
    if isinstance(exc, httpx.RequestError):
        return f"远端 MCP 网络请求失败（{type(exc).__name__}）"

    message = str(exc) or type(exc).__name__
    return _URL_QUERY.sub(r"\1?[REDACTED]", message)


async def list_remote_tools(
    endpoint: str,
    auth_type: str = "none",
    auth_config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """连接 streamable HTTP 的 MCP Server，返回其工具列表。

    返回 [{name, title, description, input_schema, output_schema, annotations}]，
    连接/超时异常向上抛。
    """
    async with asyncio.timeout(SYNC_TIMEOUT):
        endpoint, headers = await prepare_mcp_endpoint(endpoint, auth_type, auth_config or {})
        async with streamablehttp_client(endpoint, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

    tools: list[dict[str, Any]] = []
    for tool in result.tools:
        tools.append(
            {
                "name": tool.name,
                "title": tool.title,
                "description": tool.description or "",
                "input_schema": tool.inputSchema or {},
                "output_schema": tool.outputSchema or {},
                "annotations": tool.annotations.model_dump(exclude_none=True)
                if tool.annotations
                else {},
            }
        )
    return tools


async def call_remote_tool(
    endpoint: str,
    tool_name: str,
    arguments: dict[str, Any],
    auth_type: str = "none",
    auth_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Call a remote MCP tool and return its serialized MCP result."""
    async with asyncio.timeout(SYNC_TIMEOUT):
        endpoint, headers = await prepare_mcp_endpoint(endpoint, auth_type, auth_config or {})
        async with streamablehttp_client(endpoint, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
    return result.model_dump(mode="json", by_alias=True, exclude_none=True)
