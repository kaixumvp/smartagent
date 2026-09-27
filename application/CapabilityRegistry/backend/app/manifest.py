import re
from typing import Any, Optional


def slugify(name: str) -> str:
    """从展示名生成机器名（保留中英文/数字）。"""
    s = re.sub(r"[^0-9a-zA-Z一-鿿]+", "_", name.strip()).strip("_").lower()
    return s or "tool"


def new_manifest(
    display_name: str,
    description: str,
    version: str,
    tags: list[str],
    keywords: list[str],
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    provider: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """按 system-architecture.md §7 的六段结构生成 manifest。"""
    return {
        "identity": {
            "name": slugify(display_name),
            "display_name": display_name,
            "version": version,
        },
        "provider": provider,
        "metadata": {
            "description": description,
            "owner": None,
            "tags": tags,
            "keywords": keywords,
        },
        "discovery": {"enabled": False, "intents": []},
        "permission": None,
        "contract": {
            "input_schema": input_schema,
            "output_schema": output_schema,
        },
    }


def manifest_from_mcp_tool(provider: Any, mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """把 MCP list_tools() 返回的单个 tool 映射为六段 manifest。

    mcp_tool 形如 {"name", "title", "description", "input_schema",
    "output_schema", "annotations"}。display_name 取 title（缺省回退 name）；
    permission 暂不派生（权限由管理员后续配置）。
    """
    remote_tool_name = mcp_tool.get("name") or "unnamed_tool"
    display_name = mcp_tool.get("title") or remote_tool_name
    description = mcp_tool.get("description") or ""
    input_schema = mcp_tool.get("input_schema") or {}
    output_schema = mcp_tool.get("output_schema") or {}
    annotations = mcp_tool.get("annotations") or {}
    provider_segment = {
        "provider_id": str(provider.id),
        "provider_name": provider.name,
        "remote_tool_name": remote_tool_name,
    }
    return {
        "identity": {
            "name": remote_tool_name,
            "display_name": display_name,
            "version": "1.0.0",
        },
        "provider": provider_segment,
        "metadata": {
            "description": description,
            "owner": None,
            "tags": [],
            "keywords": [],
            "annotations": annotations,
        },
        "discovery": {"enabled": False, "intents": []},
        "permission": None,
        "contract": {
            "input_schema": input_schema,
            "output_schema": output_schema,
        },
    }
