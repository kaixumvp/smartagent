import asyncio
import json
import logging
import time

from src.core.state import AgentState
from src.observability.metrics import noop_metrics
from src.observability.trace import default_tracer
from src.plugins.base import InvokeContext
from src.plugins.registry import PluginRegistry
from src.ports import PermissionChecker, PermissionContext, PermissionDecision

logger = logging.getLogger(__name__)


def _coerce_result(result) -> str:
    """Normalize a plugin result (ToolResult, str, or arbitrary object) into a string."""
    if isinstance(result, str):
        return result
    if hasattr(result, "success") and hasattr(result, "output"):
        if result.success:
            return result.output if isinstance(result.output, str) else json.dumps(result.output, ensure_ascii=False)
        return f"Tool execution failed: {result.error}"
    return json.dumps(result, ensure_ascii=False, default=str)


def _single_call(state: AgentState, action: str) -> list[dict]:
    return [
        {
            "id": state.get("tool_call_id") or f"call_{action}",
            "name": action,
            "arguments": state.get("action_input") or {},
        }
    ]


def _authorize(manifest, permission_manager, permission_context, approved) -> PermissionDecision:
    if permission_manager is None or permission_context is None:
        return PermissionDecision.ALLOW
    return permission_manager.check(
        permission_context,
        "execute",
        manifest.kind,
        manifest.name,
        resource_permission=manifest.permission,
        requires_approval=manifest.requires_approval,
        approved=approved,
    )


async def run_execute(
    state: AgentState,
    registry: PluginRegistry,
    permission_manager: PermissionChecker | None = None,
    permission_context: PermissionContext | None = None,
    *,
    tracer=None,
    metrics=None,
) -> dict:
    tracer = tracer or default_tracer
    metrics = metrics or noop_metrics
    action = state.get("action")
    if not action or action == "__finish__":
        return {"last_tool_result": None}

    calls = list(state.get("tool_calls") or _single_call(state, action))

    # Authorize every call first: deny wins; any approval requirement pauses the whole round.
    approved = set(state.get("approvals") or [])
    pending: list[dict] = []
    for call in calls:
        plugin = registry.get(call["name"])
        if plugin is None:
            continue  # reported as "unknown plugin" during invocation
        decision = _authorize(plugin.manifest, permission_manager, permission_context, approved)
        if decision == PermissionDecision.DENY:
            logger.warning("execute: permission denied for %s", call["name"])
            return {"last_tool_result": f"[denied] permission denied for {call['name']}"}
        if decision == PermissionDecision.REQUIRE_APPROVAL:
            pending.append({
                "resource_type": plugin.manifest.kind,
                "resource_id": plugin.manifest.name,
                "action": call["name"],
            })

    if pending:
        names = ", ".join(p["action"] for p in pending)
        logger.info("execute: %s requires human approval", names)
        return {
            "last_tool_result": f"[approval required] {names} is pending human approval",
            "pending_approvals": pending,
            "status": "awaiting_human",
        }

    # Invoke — in parallel when the LLM returned multiple tool calls (V0.4).
    if len(calls) == 1:
        result = await _invoke_one(state, registry, calls[0], tracer, metrics)
        return {
            "last_tool_result": result,
            "tool_call_ids": [calls[0]["id"]],
            "tool_results": [result],
        }

    results = await asyncio.gather(
        *[_invoke_one(state, registry, call, tracer, metrics) for call in calls]
    )
    combined = "\n".join(f"[{call['name']}] {result}" for call, result in zip(calls, results))
    return {
        "last_tool_result": combined,
        "tool_call_ids": [call["id"] for call in calls],
        "tool_results": list(results),
    }


async def _invoke_one(state: AgentState, registry: PluginRegistry, call: dict, tracer, metrics) -> str:
    name = call["name"]
    plugin = registry.get(name)
    if plugin is None:
        logger.warning("execute: unknown plugin %s", name)
        return f"unknown plugin: {name}"
    manifest = plugin.manifest

    # Enforce the sub-agent recursion cap before delegating to a nested agent.
    if getattr(plugin, "type", None) == "agent" and state.get("subagent_depth", 0) >= state.get(
        "max_subagent_depth", 3
    ):
        logger.warning("execute: sub-agent depth limit reached for %s", name)
        return f"[refused] sub-agent depth limit reached for {name}"

    ctx = InvokeContext(
        tenant_id=state.get("tenant_id", "default"),
        user_id=state.get("user_id"),
        run_id=state.get("run_id"),
        session_id=state.get("session_id"),
        subagent_depth=state.get("subagent_depth", 0),
        trace_id=state.get("trace_id"),
    )

    action_input = dict(call.get("arguments") or {})
    if manifest.kind == "skill" and getattr(plugin, "type", None) == "prompt":
        action_input = {**action_input, "memory_ctx": state.get("memory_ctx") or []}

    start = time.perf_counter()
    with tracer.start_span(f"ouroboros.plugin.{name}", attributes={"plugin": name, "kind": manifest.kind}) as span:
        try:
            result = await registry.invoke(name, ctx, **action_input)
        except Exception as exc:  # noqa: BLE001 — log, mark span, re-raise for the runtime's retry
            logger.exception("execute: plugin %s raised", name)
            tracer.record_error(span, exc)
            raise

    metrics.incr("ouroboros.tool.calls", labels={"name": name})
    metrics.observe("ouroboros.tool.latency_ms", int((time.perf_counter() - start) * 1000), {"name": name})
    return _coerce_result(result)
