import logging

import httpx

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class HttpTool(BaseTool):
    id = "tool_http"
    name = "http"
    description = "Send an HTTP request and return the response, supporting GET/POST"
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Request URL"},
            "method": {"type": "string", "enum": ["GET", "POST"]},
            "headers": {"type": "object"},
            "body": {"type": "string"},
        },
        "required": ["url"],
    }

    async def run(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: str | None = None,
    ) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.request(method, url, headers=headers, content=body)
                return ToolResult(success=resp.is_success, output=resp.text[:4000])
        except Exception as exc:  # noqa: BLE001
            logger.warning("http tool failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))
