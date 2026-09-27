"""Assemble the plugin set referenced by an Agent config into a PluginRegistry (business adapter).

Reads the `tools` / `skills` tables (business persistence) and registers framework Plugin objects.
Legacy V0.1 `config.tools` entries are normalized to the V0.2 `config.plugins` shape.
"""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Skill, Tool
from ouroboros.plugins.manifest import parse_ref
from ouroboros.plugins.registry import PluginRegistry
from ouroboros.skills.manager import SkillManager
from ouroboros.tools.http_openapi import HttpOpenApiTool, build_url_template, load_spec, operation_to_json_schema
from ouroboros.tools.mcp import McpTool
from ouroboros.tools.registry import ToolRegistry


def extract_plugins(agent_config: dict | None) -> list[dict]:
    """Normalize agent config into a uniform list of `{"type", "ref", "config"}` entries.

    Accepts the V0.2 `plugins` array, and falls back to the legacy V0.1 `tools` array
    (treated as bare tool references).
    """
    config = agent_config or {}
    if config.get("plugins"):
        return list(config["plugins"])
    entries: list[dict] = []
    for ref in config.get("tools") or []:
        entries.append({"type": "tool", "ref": ref, "config": None})
    return entries


class PluginLoader:
    """Loads and registers the plugins referenced by an Agent config."""

    def __init__(self, tool_registry: ToolRegistry, skill_manager: SkillManager) -> None:
        self._tool_registry = tool_registry
        self._skill_manager = skill_manager

    async def load_for_agent(
        self,
        db: AsyncSession,
        tenant_id: str,
        agent_config: dict | None,
    ) -> PluginRegistry:
        registry = PluginRegistry()
        for entry in extract_plugins(agent_config):
            kind = entry.get("type") or "tool"
            ref = entry.get("ref") or ""
            if kind == "tool":
                tool = self._builtin_tool(ref) or await self._db_tool(db, tenant_id, ref)
                if tool is not None:
                    registry.register_tool(tool)
            elif kind == "skill":
                skill = await self._db_skill(db, tenant_id, ref)
                if skill is not None:
                    registry.register(skill)
            # model / knowledge / memory / node kinds are reserved for later versions.
        return registry

    def _builtin_tool(self, ref: str):
        parsed = parse_ref(ref)
        name = parsed.name if parsed else ref
        return self._tool_registry.get(name)

    async def _db_tool(self, db: AsyncSession, tenant_id: str, ref: str):
        parsed = parse_ref(ref)
        name = parsed.name if parsed else ref
        row = (
            await db.execute(select(Tool).where(Tool.name == name, Tool.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.type == "mcp":
            return McpTool(
                row.id, row.name, row.description or "", row.parameters, row.permission,
                row.endpoint or "", row.config,
            )
        if row.type == "http":
            return await self._build_http_tool(row)
        # A DB-registered builtin should already be covered by the in-process registry.
        return self._builtin_tool(name)

    async def _build_http_tool(self, row: Tool):
        """Fetch the OpenAPI spec, resolve the configured operation, and build the tool."""
        config = row.config or {}
        if not row.endpoint:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(row.endpoint)
                resp.raise_for_status()
                spec = load_spec(resp.text)
        except Exception:  # noqa: BLE001 — leave schema resolution to registration-time `parameters`
            spec = {}
        operation, url_template, method = _resolve_operation(spec, config, row.endpoint)
        parameters = row.parameters
        if not parameters.get("properties") and operation:
            parameters = operation_to_json_schema(operation)
        return HttpOpenApiTool(
            row.id, row.name, row.description or "", parameters, row.permission,
            url_template, method, config,
        )

    async def _db_skill(self, db: AsyncSession, tenant_id: str, ref: str):
        parsed = parse_ref(ref)
        if parsed is None or parsed.kind != "skill":
            return None
        stmt = select(Skill).where(Skill.name == parsed.name, Skill.tenant_id == tenant_id)
        if parsed.version:
            stmt = stmt.where(Skill.version == parsed.version)
        else:
            stmt = stmt.where(Skill.is_latest.is_(True))
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return self._skill_manager.build(
            {
                "name": row.name,
                "version": row.version,
                "type": row.type,
                "description": row.description,
                "manifest": row.manifest,
                "body": row.body,
            }
        )


def _resolve_operation(spec: dict, config: dict, endpoint: str) -> tuple[dict | None, str, str]:
    """Pick an OpenAPI operation by operation_id or path+method; fall back to the raw endpoint."""
    paths = spec.get("paths") or {}
    servers = spec.get("servers") or [{"url": endpoint.rsplit("/", 1)[0]}]
    method = (config.get("method") or "get").lower()
    for path, item in paths.items():
        ops = {k: v for k, v in item.items() if k in {"get", "post", "put", "patch", "delete"}}
        for m, operation in ops.items():
            if config.get("operation_id") and operation.get("operationId") == config["operation_id"]:
                return operation, build_url_template(servers, path), m
            if config.get("path") == path and m == method:
                return operation, build_url_template(servers, path), m
    return None, endpoint, config.get("method", "get")
