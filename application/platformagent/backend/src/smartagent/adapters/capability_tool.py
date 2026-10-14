from typing import Any

from smartagent.adapters.capability_registry import CapabilityRegistryClient
from ouroboros.tools.base import BaseTool, ToolResult


class CapabilityRegistryTool(BaseTool):
    def __init__(
        self,
        *,
        client: CapabilityRegistryClient,
        tool_id: str,
        name: str,
        description: str,
        parameters: dict[str, Any],
        permission: str = "read",
    ) -> None:
        self.id = f"capability_{tool_id}"
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}, "required": []}
        self.permission = permission
        self._client = client
        self._tool_id = tool_id

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            result = await self._client.call_tool(self._tool_id, kwargs)
            is_error = bool(result.get("isError"))
            return ToolResult(success=not is_error, output=result)
        except Exception as exc:  # noqa: BLE001 - report integration failures as tool results
            return ToolResult(success=False, output="", error=str(exc))


class CapabilityMcpTool(CapabilityRegistryTool):
    """Expose a Capability Registry MCP endpoint as a standard runtime Tool."""


class CapabilityApiTool(CapabilityRegistryTool):
    """Expose a Capability Registry HTTP API endpoint as a standard runtime Tool."""
