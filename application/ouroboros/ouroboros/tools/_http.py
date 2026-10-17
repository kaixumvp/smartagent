"""Shared HTTP request helper for the HTTP tools.

Both ``HttpTool`` (free-form GET/POST) and ``HttpOpenApiTool`` (spec-bound) wrap the same
``httpx`` call with the same normalization: truncate the response to a bounded length and turn
transport/HTTP errors into ``success=False`` rather than raising.
"""

import logging

import httpx

from ouroboros.tools.base import ToolResult

logger = logging.getLogger(__name__)

_TRUNCATE = 4000


async def http_request(method: str, url: str, *, timeout: float, **kwargs) -> ToolResult:
    """Send an HTTP request and normalize the outcome into a ``ToolResult``."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)
            return ToolResult(success=resp.is_success, output=resp.text[:_TRUNCATE])
    except Exception as exc:  # noqa: BLE001
        logger.warning("http request failed: %s", exc)
        return ToolResult(success=False, output="", error=str(exc))
