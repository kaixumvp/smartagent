"""Minimal MCP (Model Context Protocol) client + tool adapter.

V0.2 targets the *streamable HTTP* transport of MCP: JSON-RPC 2.0 requests POSTed to the
server endpoint. A single `tools` row maps to a single MCP tool (`name` is the MCP tool name,
`endpoint` the server URL, `config` may carry headers/auth).
"""

import json
import logging
from typing import Any

import httpx

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class McpClient:
    """Thin JSON-RPC 2.0 client over streamable HTTP for MCP servers."""

    def __init__(self, endpoint: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> None:
        self._endpoint = endpoint
        self._headers = headers or {}
        self._timeout = timeout
        self._next_id = 1

    async def _rpc(self, method: str, params: dict | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        self._next_id += 1
        headers = {"Content-Type": "application/json", **self._headers}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})

    async def initialize(self) -> None:
        await self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smartagent", "version": "0.2.0"}})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        # MCP content blocks are typically {"type": "text", "text": "..."}.
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)


class McpTool(BaseTool):
    """Run-based tool that dispatches to an MCP server tool of the same name."""

    def __init__(
        self,
        id_: str,
        name: str,
        description: str,
        parameters: dict,
        permission: str,
        endpoint: str,
        config: dict | None = None,
    ) -> None:
        self.id = id_
        self.name = name
        self.description = description
        self.parameters = parameters
        self.permission = permission
        self.endpoint = endpoint
        self.config = config or {}

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            headers = (self.config.get("auth") or {}).get("headers") or {}
            client = McpClient(self.endpoint, headers=headers)
            await client.initialize()
            output = await client.call_tool(self.name, kwargs)
            return ToolResult(success=True, output=output)
        except Exception as exc:  # noqa: BLE001 — surface MCP failures as a tool error
            logger.warning("mcp tool %s failed: %s", self.name, exc)
            return ToolResult(success=False, output="", error=str(exc))
