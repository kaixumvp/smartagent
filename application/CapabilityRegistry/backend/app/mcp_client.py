import asyncio
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# 连接 + list_tools 的整体超时（秒）
SYNC_TIMEOUT = 30


async def list_remote_tools(
    endpoint: str, credential_ref: Optional[str] = None
) -> list[dict[str, Any]]:
    """连接 streamable HTTP 的 MCP Server，返回其工具列表。

    返回 [{name, title, description, input_schema, output_schema, annotations}]，
    连接/超时异常向上抛。credential_ref 为密钥引用（不落明文），本版仅占位，未解析实际凭据。
    """
    async with asyncio.timeout(SYNC_TIMEOUT):
        async with streamablehttp_client(endpoint) as (read, write, _):
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
