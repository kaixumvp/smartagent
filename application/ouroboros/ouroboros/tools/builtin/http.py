from ouroboros.tools._http import http_request
from ouroboros.tools.base import BaseTool, ToolResult


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
        return await http_request(method, url, timeout=10.0, headers=headers, content=body)
