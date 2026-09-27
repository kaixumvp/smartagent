"""HTTP tool adapter backed by an OpenAPI spec.

A single `tools` row maps to a single OpenAPI operation. The loader (plugins/loader.py)
fetches the spec, picks the operation (by `config.operation_id` or `config.path`+`method`),
generates the JSON Schema for its parameters, and constructs this tool with a concrete URL
template and HTTP config.
"""

import json
import logging
from typing import Any

import httpx

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def load_spec(raw: str) -> dict:
    """Parse an OpenAPI document from JSON or YAML (YAML requires PyYAML to be installed)."""
    text = raw.strip()
    if text.startswith("{"):
        return json.loads(text)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise RuntimeError("OpenAPI YAML specs require PyYAML; install it or provide JSON") from exc
    return yaml.safe_load(text)


def build_url_template(servers: list[dict], path: str) -> str:
    """Join the first server base URL with the path template (e.g. /orders/{order_id})."""
    base = servers[0]["url"].rstrip("/") if servers else ""
    return base + path


def operation_to_json_schema(operation: dict) -> dict:
    """Derive a JSON Schema for an operation's parameters + requestBody.

    OpenAPI `parameters` (query/path/header) map to `properties`; `requestBody` (JSON) maps to
    a single `body` property. Required marks propagate from OpenAPI `required` lists.
    """
    properties: dict = {}
    required: list[str] = []
    for param in operation.get("parameters", []):
        name = param.get("name")
        if not name:
            continue
        schema = param.get("schema", {"type": "string"})
        schema.setdefault("description", param.get("description", ""))
        properties[name] = schema
        if param.get("required"):
            required.append(name)
    body = operation.get("requestBody", {}).get("content", {}).get("application/json", {})
    if body:
        properties["body"] = body.get("schema", {"type": "object"})
    return {"type": "object", "properties": properties, "required": required}


class HttpOpenApiTool(BaseTool):
    """Run-based tool that performs the HTTP call described by a resolved OpenAPI operation."""

    def __init__(
        self,
        id_: str,
        name: str,
        description: str,
        parameters: dict,
        permission: str,
        url_template: str,
        method: str,
        config: dict | None = None,
    ) -> None:
        self.id = id_
        self.name = name
        self.description = description
        self.parameters = parameters
        self.permission = permission
        self.url_template = url_template
        self.method = method.upper()
        self.config = config or {}

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            body = kwargs.pop("body", None)
            # Separate path params (embedded in the template) from query params (the rest).
            url = self.url_template.format(**kwargs)
            query = {k: v for k, v in kwargs.items() if f"{{{k}}}" not in self.url_template}
            headers = dict(self.config.get("headers") or {})
            auth = self.config.get("auth") or {}
            if auth.get("type") == "api_key":
                headers[auth.get("header", "X-Api-Key")] = auth.get("key", "")
            async with httpx.AsyncClient(timeout=float(self.config.get("timeout", 30))) as client:
                resp = await client.request(
                    self.method, url, params=query or None, json=body, headers=headers
                )
                return ToolResult(success=resp.is_success, output=resp.text[:4000])
        except Exception as exc:  # noqa: BLE001
            logger.warning("http tool %s failed: %s", self.name, exc)
            return ToolResult(success=False, output="", error=str(exc))
