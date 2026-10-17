import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api_tool_executor import ApiToolTimeoutError, call_api_tool
from .mcp_auth import decrypt_auth_config
from .mcp_client import call_remote_tool, describe_mcp_error
from .models import (
    ApiService,
    Provider,
    Tool,
    Workflow,
    WorkflowInteraction,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowVersion,
)

MAX_NODES = 30
MAX_EDGES = 60
MAX_CONTEXT_BYTES = 1_048_576
_PATH_PART = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_json_value(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: schema must be an object")
    expected = schema.get("type")
    actual_type = (
        "null" if value is None else "boolean" if isinstance(value, bool)
        else "object" if isinstance(value, dict) else "array" if isinstance(value, list)
        else "integer" if isinstance(value, int) else "number" if isinstance(value, float)
        else "string" if isinstance(value, str) else "unknown"
    )
    if expected and not (
        actual_type == expected
        or expected == "number" and actual_type == "integer"
    ):
        raise ValueError(f"{path}: expected {expected}, got {actual_type}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value is not in enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError(f"{path}: schema properties must be an object")
        for required in schema.get("required", []):
            if required not in value:
                raise ValueError(f"{path}.{required}: field is required")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise ValueError(f"{path}: unexpected fields: {', '.join(sorted(extra))}")
        for key, item in value.items():
            if key in properties:
                _validate_json_value(item, properties[key], f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path}: too few array items")
        if len(value) > schema.get("maxItems", 1000):
            raise ValueError(f"{path}: too many array items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_json_value(item, item_schema, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path}: string is too short")
        if len(value) > schema.get("maxLength", 100_000):
            raise ValueError(f"{path}: string is too long")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: value is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path}: value is above maximum")


def _validate_schema_definition(schema: Any, path: str = "$schema", depth: int = 0) -> None:
    if depth > 16 or not isinstance(schema, dict):
        raise ValueError(f"{path}: JSON Schema must be an object with maximum depth 16")
    supported_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in supported_types:
        raise ValueError(f"{path}: unsupported JSON Schema type")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{path}: properties must be an object")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError(f"{path}: required must be an array of strings")
    if any(item not in properties for item in required):
        raise ValueError(f"{path}: required fields must be declared in properties")
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or len(enum) > 1000):
        raise ValueError(f"{path}: enum must be an array of at most 1000 values")
    for name, child in properties.items():
        if not isinstance(name, str):
            raise ValueError(f"{path}: property names must be strings")
        _validate_schema_definition(child, f"{path}.properties.{name}", depth + 1)
    if "items" in schema:
        _validate_schema_definition(schema["items"], f"{path}.items", depth + 1)


def _node_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, str) and value.startswith("$.node."):
        parts = value[7:].split(".")
        if parts and _PATH_PART.fullmatch(parts[0]):
            references.add(parts[0])
    elif isinstance(value, dict):
        for child in value.values():
            references.update(_node_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(_node_references(child))
    return references


def validate_definition(db: Session, definition: dict[str, Any]) -> None:
    if definition.get("schema_version", 1) != 1:
        raise ValueError("Unsupported Workflow schema_version")
    for schema_key in ("input_schema", "output_schema"):
        if schema_key in definition:
            _validate_schema_definition(definition[schema_key], schema_key)
    nodes = definition.get("nodes")
    edges = definition.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Workflow definition requires nodes and edges arrays")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError(f"Workflow is limited to {MAX_NODES} nodes and {MAX_EDGES} edges")
    if not nodes:
        raise ValueError("Workflow must contain nodes")
    ids: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise ValueError("Every node must have a string id")
        node_id = node["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", node_id) or node_id in ids:
            raise ValueError(f"Invalid or duplicate node id: {node_id}")
        if node.get("type") not in {
            "start", "tool", "api", "condition", "transform", "human_input", "approval", "end"
        }:
            raise ValueError(f"Node '{node_id}' has an unsupported type")
        ids[node_id] = node
    for condition in definition.get("preconditions", []):
        _validate_condition(condition)
    starts = [node for node in nodes if node["type"] == "start"]
    ends = [node for node in nodes if node["type"] == "end"]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("Workflow must contain exactly one start and one end node")

    graph: dict[str, list[str]] = {node_id: [] for node_id in ids}
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in ids}
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") not in ids or edge.get("to") not in ids:
            raise ValueError("Every edge must reference existing nodes")
        source = edge["from"]
        target = edge["to"]
        graph[source].append(target)
        outgoing[source].append(edge)
        branch = edge.get("branch")
        kind = ids[source]["type"]
        if kind == "condition" and not isinstance(branch, str):
            raise ValueError(f"Condition edge from '{source}' requires a branch id")
        if kind in {"approval", "human_input"} and branch not in (
            {"approved", "rejected", "returned", "expired"} if kind == "approval" else {"expired"}
        ):
            if branch is not None:
                raise ValueError(f"Node '{source}' has an invalid result branch")
        if kind not in {"condition", "approval", "human_input"} and branch is not None:
            raise ValueError(f"Node '{source}' does not support branch edges")
    if not outgoing[starts[0]["id"]]:
        raise ValueError("Start node must have an outgoing edge")
    for node_id, node in ids.items():
        if node["type"] == "condition":
            branches = node.get("branches", [])
            if not isinstance(branches, list) or not branches:
                raise ValueError(f"Condition '{node_id}' requires branches")
            branch_ids = [branch.get("id") for branch in branches if isinstance(branch, dict)]
            if len(branch_ids) != len(branches) or len(set(branch_ids)) != len(branch_ids):
                raise ValueError(f"Condition '{node_id}' has invalid or duplicate branches")
            if not any(branch.get("default") is True for branch in branches):
                raise ValueError(f"Condition '{node_id}' requires a default branch")
            if len([branch for branch in branches if branch.get("default") is True]) != 1:
                raise ValueError(f"Condition '{node_id}' may have only one default branch")
            if set(branch_ids) != {edge.get("branch") for edge in outgoing[node_id]}:
                raise ValueError(f"Condition '{node_id}' must have exactly one edge for each branch")
            for branch in branches:
                if branch.get("default") is not True:
                    _validate_condition(branch.get("when"))
        elif node["type"] == "approval":
            branches = {edge.get("branch") for edge in outgoing[node_id]}
            if not {"approved", "rejected"}.issubset(branches):
                raise ValueError(f"Approval '{node_id}' requires approved and rejected edges")
            if node.get("on_expire", "fail") == "expired" and "expired" not in branches:
                raise ValueError(f"Approval '{node_id}' requires an expired edge")
        elif node["type"] == "human_input":
            success_edges = [edge for edge in outgoing[node_id] if edge.get("branch") is None]
            expired_edges = [edge for edge in outgoing[node_id] if edge.get("branch") == "expired"]
            if len(success_edges) != 1 or len(outgoing[node_id]) != len(success_edges) + len(expired_edges):
                raise ValueError(f"Human input '{node_id}' requires one success edge and at most one expired edge")
            if node.get("on_expire", "fail") == "expired" and not expired_edges:
                raise ValueError(f"Human input '{node_id}' requires an expired edge")
        elif node["type"] != "end" and len(outgoing[node_id]) != 1:
            raise ValueError(f"Node '{node_id}' must have exactly one outgoing edge")
        if node["type"] in {"tool", "api"}:
            try:
                tool_id = uuid.UUID(str(node.get("tool_id")))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Node '{node_id}' requires a valid tool_id") from exc
            tool = db.get(Tool, tool_id)
            expected_source = "mcp" if node["type"] == "tool" else "api"
            if tool is None or tool.source != expected_source or not tool.enabled or tool.lifecycle_state != "active":
                raise ValueError(f"Node '{node_id}' references a missing, disabled, or inactive Tool")
        if node["type"] == "human_input":
            schema = node.get("input_schema")
            if not isinstance(schema, dict) or schema.get("type", "object") != "object":
                raise ValueError(f"Human input node '{node_id}' requires an object input_schema")
            _validate_schema_definition(schema, f"nodes.{node_id}.input_schema")
        if node["type"] == "approval" and node.get("on_expire", "fail") not in {"fail", "expired"}:
            raise ValueError(f"Approval '{node_id}' has invalid on_expire policy")
        if node["type"] == "human_input" and node.get("on_expire", "fail") not in {"fail", "expired"}:
            raise ValueError(f"Human input '{node_id}' has invalid on_expire policy")
        timeout = node.get("timeout_seconds")
        if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 2_592_000):
            raise ValueError(f"Node '{node_id}' timeout_seconds must be between 1 and 2592000")
        for condition in node.get("preconditions", []):
            _validate_condition(condition)
        for condition in node.get("postconditions", []):
            _validate_condition(condition)
        if node.get("on_precondition_fail", "fail") not in {"fail", "skip_to"}:
            raise ValueError(f"Node '{node_id}' has invalid on_precondition_fail")
        if node.get("on_precondition_fail") == "skip_to" and node.get("skip_to") not in ids:
            raise ValueError(f"Node '{node_id}' skip_to must reference an existing node")
        if node.get("on_precondition_fail") == "skip_to" and node["skip_to"] not in graph[node_id]:
            raise ValueError(f"Node '{node_id}' skip_to must be a direct outgoing node")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("Workflow graph must be acyclic")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in graph[node_id]:
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(starts[0]["id"])
    if len(visited) != len(ids):
        raise ValueError("Workflow contains unreachable nodes")
    reverse: dict[str, list[str]] = {node_id: [] for node_id in ids}
    for source, targets in graph.items():
        for target in targets:
            reverse[target].append(source)
    can_reach_end = {ends[0]["id"]}
    stack = [ends[0]["id"]]
    while stack:
        for parent in reverse[stack.pop()]:
            if parent not in can_reach_end:
                can_reach_end.add(parent)
                stack.append(parent)
    if can_reach_end != set(ids):
        raise ValueError("Every workflow node must be able to reach the end node")
    for node_id, node in ids.items():
        ancestors: set[str] = set()
        stack = list(reverse[node_id])
        while stack:
            parent = stack.pop()
            if parent not in ancestors:
                ancestors.add(parent)
                stack.extend(reverse[parent])
        expressions = [
            node.get("input_mapping"),
            node.get("output_mapping"),
            node.get("display_mapping"),
            node.get("preconditions"),
            node.get("postconditions"),
            [branch.get("when") for branch in node.get("branches", []) if isinstance(branch, dict)],
        ]
        for reference in set().union(*(_node_references(item) for item in expressions)):
            if reference not in ids:
                raise ValueError(f"Node '{node_id}' references unknown node '{reference}'")
            if reference not in ancestors:
                raise ValueError(f"Node '{node_id}' references node '{reference}' before it executes")


def _read_path(context: dict[str, Any], path: str) -> Any:
    if not path.startswith("$."):
        raise ValueError(f"Unsupported context path: {path}")
    parts = path[2:].split(".")
    if not parts or any(not _PATH_PART.fullmatch(part) for part in parts):
        raise ValueError(f"Unsupported context path: {path}")
    root = parts.pop(0)
    if root not in {"input", "workflow", "node"}:
        raise ValueError(f"Unsupported context path: {path}")
    if root == "node":
        if not parts:
            raise ValueError("Node paths must include a node id")
        current: Any = context.get("node", {}).get(parts.pop(0))
    else:
        current = context.get(root)
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _resolve(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$."):
        return _read_path(context, value)
    if isinstance(value, dict):
        return {key: _resolve(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, context) for item in value]
    return value


def _evaluate(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        raise ValueError("Condition expression must be an object")
    op = condition.get("op")
    left = _resolve(condition.get("left"), context)
    right = _resolve(condition.get("right"), context)
    if op == "exists":
        return left is not None
    if op == "equals":
        return left == right
    if op == "not_equals":
        return left != right
    if op == "gt":
        return left is not None and right is not None and left > right
    if op == "gte":
        return left is not None and right is not None and left >= right
    if op == "lt":
        return left is not None and right is not None and left < right
    if op == "lte":
        return left is not None and right is not None and left <= right
    if op == "in":
        return isinstance(right, (list, str)) and left in right
    if op == "contains":
        return isinstance(left, (list, str, dict)) and right in left
    if op == "starts_with":
        return isinstance(left, str) and isinstance(right, str) and left.startswith(right)
    if op == "and":
        return all(_evaluate(item, context) for item in condition.get("args", []))
    if op == "or":
        return any(_evaluate(item, context) for item in condition.get("args", []))
    if op == "not":
        return not _evaluate(condition.get("arg", {}), context)
    raise ValueError(f"Unsupported condition operator: {op}")


def _validate_condition(condition: Any, depth: int = 0) -> None:
    if depth > 12 or not isinstance(condition, dict):
        raise ValueError("Condition expression must be an object with maximum depth 12")
    op = condition.get("op")
    if op not in {
        "equals", "not_equals", "gt", "gte", "lt", "lte", "in", "contains",
        "starts_with", "exists", "and", "or", "not",
    }:
        raise ValueError(f"Unsupported condition operator: {op}")
    if op in {"and", "or"}:
        args = condition.get("args")
        if not isinstance(args, list) or not args or len(args) > 50:
            raise ValueError(f"Condition operator '{op}' requires 1 to 50 args")
        for item in args:
            _validate_condition(item, depth + 1)
    elif op == "not":
        _validate_condition(condition.get("arg"), depth + 1)
    else:
        if not isinstance(condition.get("left"), str):
            raise ValueError(f"Condition operator '{op}' requires a left path")
        _read_path({"input": {}, "workflow": {}, "node": {}}, condition["left"])
        if op != "exists" and "right" not in condition:
            raise ValueError(f"Condition operator '{op}' requires a right value")
        right = condition.get("right")
        if isinstance(right, str) and right.startswith("$."):
            _read_path({"input": {}, "workflow": {}, "node": {}}, right)


def _next_node(definition: dict[str, Any], node_id: str, branch: str | None = None) -> str | None:
    edges = [edge for edge in definition["edges"] if edge["from"] == node_id]
    if branch is not None:
        edges = [edge for edge in edges if edge.get("branch") == branch]
    return edges[0]["to"] if edges else None


def _call_tool(db: Session, tool: Tool, arguments: dict[str, Any]) -> Any:
    if tool.source == "api":
        service = db.get(ApiService, tool.api_service_id) if tool.api_service_id else None
        if service is None:
            raise RuntimeError("API service not found")
        db.commit()
        try:
            return asyncio.run(call_api_tool(service, tool, arguments))
        except ApiToolTimeoutError as exc:
            # 节点按超时处理，其余错误原样冒泡（错误分类由 ApiToolCallError 子类承载）
            raise TimeoutError(str(exc)) from exc
    if tool.source == "mcp" and tool.provider_id and tool.remote_tool_name:
        provider = db.get(Provider, tool.provider_id)
        if provider is None:
            raise RuntimeError("MCP Provider not found")
        auth_config = decrypt_auth_config(provider.auth_config_encrypted)
        db.commit()
        try:
            return asyncio.run(
                call_remote_tool(
                    provider.endpoint,
                    tool.remote_tool_name,
                    arguments,
                    provider.auth_type,
                    auth_config,
                )
            )
        except TimeoutError:
            raise
        except Exception as exc:
            description = describe_mcp_error(exc)
            if "超时" in description:
                raise TimeoutError(description) from exc
            raise RuntimeError(description) from exc
    raise RuntimeError("Workflow Tool reference is no longer available")


def _interaction_view(item: WorkflowInteraction) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "workflow_run_id": str(item.workflow_run_id),
        "node_id": item.node_id,
        "kind": item.kind,
        "status": item.status,
        "title": item.title,
        "prompt": item.prompt,
        "form_schema": item.form_schema,
        "display_data": item.display_data,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "revision": item.revision,
        "response": item.response,
        "response_comment": item.response_comment,
    }


def _run_view(run: WorkflowRun, interaction: WorkflowInteraction | None = None) -> dict[str, Any]:
    return {
        "workflow_run_id": str(run.id),
        "status": run.status,
        "current_node_id": run.current_node_id,
        "output": run.output,
        "error": run.error,
        "interaction": _interaction_view(interaction) if interaction else None,
    }


def _node_output_context(context: dict[str, Any], node_id: str, output: Any) -> dict[str, Any]:
    node_context = dict(context.get("node") or {})
    node_context[node_id] = {"output": output}
    updated_context = {**context, "node": node_context}
    if len(json.dumps(updated_context, ensure_ascii=False, default=str).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Workflow context exceeds the 1 MiB limit")
    return updated_context


def _set_node_output(run: WorkflowRun, node_id: str, output: Any) -> None:
    run.context = _node_output_context(run.context, node_id, output)


def _new_interaction(
    db: Session, run: WorkflowRun, node: dict[str, Any]
) -> WorkflowInteraction:
    interaction = WorkflowInteraction(
        workflow_run_id=run.id,
        node_id=node["id"],
        kind="input" if node["type"] == "human_input" else "approval",
        title=node.get("title") or ("补充信息" if node["type"] == "human_input" else "待审批"),
        prompt=node.get("prompt") or "",
        form_schema=node.get("input_schema") or {},
        display_data=_resolve(node.get("display_mapping") or node.get("display_data") or {}, run.context),
        resume_context=run.context,
        due_at=(
            datetime.now(timezone.utc)
            + timedelta(seconds=min(max(int(node.get("timeout_seconds", 86400)), 1), 2_592_000))
            if node.get("timeout_seconds") is not None
            else None
        ),
    )
    db.add(interaction)
    db.flush()
    run.status = "waiting_for_input" if interaction.kind == "input" else "waiting_for_approval"
    run.current_node_id = node["id"]
    db.commit()
    db.refresh(interaction)
    return interaction


def _execute_from(
    db: Session,
    run: WorkflowRun,
    version: WorkflowVersion,
    first_node_id: str | None,
) -> dict[str, Any]:
    definition = version.definition
    nodes = {node["id"]: node for node in definition["nodes"]}
    cursor = first_node_id
    try:
        while cursor:
            node = nodes[cursor]
            node_type = node["type"]
            run.current_node_id = cursor
            node_run = WorkflowNodeRun(workflow_run_id=run.id, node_id=cursor, status="running")
            db.add(node_run)
            db.commit()
            failed_precondition = next(
                (condition for condition in node.get("preconditions", []) if not _evaluate(condition, run.context)),
                None,
            )
            if failed_precondition is not None:
                if node.get("on_precondition_fail", "fail") == "skip_to":
                    node_run.status = "skipped"
                    node_run.output = {"skipped": True}
                    node_run.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    cursor = node["skip_to"]
                    continue
                raise ValueError(f"PRECONDITION_FAILED at node '{cursor}'")
            if node_type == "end":
                output = _resolve(node.get("output_mapping") or {}, run.context)
                _validate_json_value(output, definition.get("output_schema") or {"type": "object"})
                run.output = output
                run.status = "succeeded"
                run.current_node_id = None
                run.finished_at = datetime.now(timezone.utc)
                node_run.status = "succeeded"
                node_run.output = output
                node_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return _run_view(run)
            if node_type == "start":
                result: Any = {"accepted": True}
            elif node_type == "transform":
                result = _resolve(node.get("output_mapping") or node.get("input_mapping") or {}, run.context)
            elif node_type == "condition":
                selected = next(
                    (branch for branch in node["branches"] if not branch.get("default") and _evaluate(branch["when"], run.context)),
                    next(branch for branch in node["branches"] if branch.get("default")),
                )
                condition_output = {"branch": selected["id"]}
                _set_node_output(run, cursor, condition_output)
                node_run.status = "succeeded"
                node_run.output = condition_output
                node_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                cursor = _next_node(definition, node["id"], selected["id"])
                continue
            elif node_type in {"human_input", "approval"}:
                node_run.status = "waiting"
                node_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                interaction = _new_interaction(db, run, node)
                return _run_view(run, interaction)
            elif node_type in {"tool", "api"}:
                try:
                    tool = db.get(Tool, uuid.UUID(node["tool_id"]))
                except (ValueError, TypeError):
                    tool = None
                if tool is None or not tool.enabled or tool.lifecycle_state != "active":
                    raise RuntimeError("Referenced Capability Tool is no longer active")
                arguments = _resolve(node.get("input_mapping") or {}, run.context)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool input_mapping must resolve to a JSON object")
                _validate_json_value(
                    arguments,
                    (tool.manifest or {}).get("contract", {}).get("input_schema") or {"type": "object"},
                )
                node_run.input_data = arguments
                result = _call_tool(db, tool, arguments)
            else:
                raise ValueError(f"Unsupported Workflow node type: {node_type}")
            if len(json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")) > MAX_CONTEXT_BYTES:
                raise ValueError("Node result exceeds the 1 MiB limit")
            for condition in node.get("postconditions", []):
                if not _evaluate(condition, {"input": run.context["input"], "workflow": run.context["workflow"], "node": {**run.context["node"], cursor: {"output": result}}}):
                    raise ValueError(f"POSTCONDITION_FAILED at node '{cursor}'")
            _set_node_output(run, cursor, result)
            node_run.status = "succeeded"
            node_run.output = result
            node_run.finished_at = datetime.now(timezone.utc)
            db.commit()
            cursor = _next_node(definition, cursor)
        raise ValueError("Workflow execution reached no terminal node")
    except Exception as exc:
        db.rollback()
        current = db.get(WorkflowRun, run.id)
        if current is not None:
            failed_status = "timed_out" if isinstance(exc, TimeoutError) else "failed"
            current.status = failed_status
            current.error = {
                "code": "PRECONDITION_FAILED" if "PRECONDITION_FAILED" in str(exc) else "WORKFLOW_NODE_FAILED",
                "message": str(exc)[:1000],
                "node_id": current.current_node_id,
            }
            current.finished_at = datetime.now(timezone.utc)
            if current.current_node_id:
                failed_node = (
                    db.query(WorkflowNodeRun)
                    .filter_by(workflow_run_id=current.id, node_id=current.current_node_id, status="running")
                    .order_by(WorkflowNodeRun.started_at.desc())
                    .first()
                )
                if failed_node:
                    failed_node.status = failed_status
                    failed_node.error = current.error
                    failed_node.finished_at = current.finished_at
            db.commit()
            return _run_view(current)
        raise


def start_run(
    db: Session,
    workflow: Workflow,
    version: WorkflowVersion,
    arguments: dict[str, Any],
    context: dict[str, Any],
    idempotency_key: str | None,
    correlation_id: str | None,
) -> dict[str, Any]:
    if len(json.dumps(arguments, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise HTTPException(status_code=413, detail="Workflow input exceeds 1 MiB")
    if len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise HTTPException(status_code=413, detail="Workflow context exceeds 1 MiB")
    if idempotency_key:
        existing = (
            db.query(WorkflowRun)
            .filter_by(workflow_id=workflow.id, idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            interaction = (
                db.query(WorkflowInteraction)
                .filter_by(workflow_run_id=existing.id, status="open")
                .order_by(WorkflowInteraction.id.desc())
                .first()
            )
            return _run_view(existing, interaction)
    try:
        _validate_json_value(arguments, version.definition.get("input_schema") or {"type": "object"})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        status="running",
        idempotency_key=idempotency_key,
        input_data=arguments,
        context={"input": arguments, "workflow": context, "node": {}},
        correlation_id=correlation_id,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not idempotency_key:
            raise
        existing = (
            db.query(WorkflowRun)
            .filter_by(workflow_id=workflow.id, idempotency_key=idempotency_key)
            .first()
        )
        if existing is None:
            raise
        interaction = (
            db.query(WorkflowInteraction)
            .filter_by(workflow_run_id=existing.id, status="open")
            .order_by(WorkflowInteraction.id.desc())
            .first()
        )
        return _run_view(existing, interaction)
    db.refresh(run)
    try:
        for condition in version.definition.get("preconditions", []):
            if not _evaluate(condition, run.context):
                raise ValueError("PRECONDITION_FAILED at Workflow entry")
    except Exception as exc:
        run.status = "failed"
        run.error = {"code": "PRECONDITION_FAILED", "message": str(exc)[:1000]}
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return _run_view(run)
    first = _next_node(version.definition, next(n["id"] for n in version.definition["nodes"] if n["type"] == "start"))
    return _execute_from(db, run, version, first)


def queue_interaction_resume(
    db: Session,
    interaction: WorkflowInteraction,
    response: dict[str, Any],
    comment: str | None,
    decision: str | None = None,
) -> dict[str, Any]:
    run = db.get(WorkflowRun, interaction.workflow_run_id)
    if run is None or run.status not in {"waiting_for_input", "waiting_for_approval"}:
        raise HTTPException(status_code=409, detail="Workflow run is no longer waiting")
    version = db.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="Workflow version is unavailable")
    node = next(item for item in version.definition["nodes"] if item["id"] == interaction.node_id)
    if interaction.kind == "input":
        try:
            _validate_json_value(response, interaction.form_schema or {"type": "object"})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        node_output = response
        next_cursor = _next_node(version.definition, node["id"])
        try:
            resumed_context = _node_output_context(interaction.resume_context, node["id"], node_output)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        interaction_status = "submitted"
    else:
        if decision not in {"approve", "reject", "return"}:
            raise HTTPException(status_code=422, detail="Decision must be approve, reject, or return")
        branch = {"approve": "approved", "reject": "rejected", "return": "returned"}[decision]
        node_output = {"decision": decision, "comment": comment}
        next_cursor = _next_node(version.definition, node["id"], branch)
        if next_cursor is None and decision == "return":
            raise HTTPException(status_code=422, detail="This approval node has no return path")
        try:
            resumed_context = _node_output_context(interaction.resume_context, node["id"], node_output)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        interaction_status = {"approve": "approved", "reject": "rejected", "return": "returned"}[decision]
    now = datetime.now(timezone.utc)
    claimed = db.execute(
        update(WorkflowInteraction)
        .where(
            WorkflowInteraction.id == interaction.id,
            WorkflowInteraction.status == "open",
            WorkflowInteraction.revision == interaction.revision,
        )
        .values(
            status=interaction_status,
            response=response if interaction.kind == "input" else node_output,
            response_comment=comment,
            completed_at=now,
            revision=WorkflowInteraction.revision + 1,
        )
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Interaction was already completed or changed")
    queued = db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == run.id,
            WorkflowRun.status == ("waiting_for_input" if interaction.kind == "input" else "waiting_for_approval"),
        )
        .values(status="queued", context=resumed_context, current_node_id=next_cursor)
    )
    if queued.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Workflow run is no longer waiting")
    node_run = (
        db.query(WorkflowNodeRun)
        .filter_by(workflow_run_id=run.id, node_id=node["id"], status="waiting")
        .order_by(WorkflowNodeRun.started_at.desc())
        .first()
    )
    if node_run:
        node_run.status = interaction_status
        node_run.output = node_output
        node_run.finished_at = now
    db.commit()
    db.expire(run)
    db.refresh(run)
    return _run_view(run)


def process_queued_workflow_runs(db: Session) -> int:
    run_ids = [
        row[0]
        for row in (
            db.query(WorkflowRun.id)
            .filter(WorkflowRun.status == "queued")
            .order_by(WorkflowRun.started_at)
            .limit(10)
            .all()
        )
    ]
    processed = 0
    for run_id in run_ids:
        claimed = db.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id, WorkflowRun.status == "queued")
            .values(status="running")
        )
        if claimed.rowcount != 1:
            db.rollback()
            continue
        db.commit()
        run = db.get(WorkflowRun, run_id)
        version = db.get(WorkflowVersion, run.workflow_version_id) if run else None
        if run is None:
            continue
        if version is None:
            run.status = "failed"
            run.error = {"code": "WORKFLOW_VERSION_MISSING"}
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            continue
        _execute_from(db, run, version, run.current_node_id)
        processed += 1
    return processed


def expire_due_interactions(db: Session) -> int:
    now = datetime.now(timezone.utc)
    due_items = (
        db.query(WorkflowInteraction)
        .filter(
            WorkflowInteraction.status == "open",
            WorkflowInteraction.due_at.is_not(None),
            WorkflowInteraction.due_at <= now,
        )
        .limit(50)
        .all()
    )
    expired = 0
    for item in due_items:
        claimed = db.execute(
            update(WorkflowInteraction)
            .where(
                WorkflowInteraction.id == item.id,
                WorkflowInteraction.status == "open",
                WorkflowInteraction.revision == item.revision,
            )
            .values(status="processing")
        )
        if claimed.rowcount != 1:
            db.rollback()
            continue
        run = db.get(WorkflowRun, item.workflow_run_id)
        version = db.get(WorkflowVersion, run.workflow_version_id) if run else None
        if run is None or version is None:
            item.status = "expired"
            db.commit()
            continue
        expected_status = "waiting_for_input" if item.kind == "input" else "waiting_for_approval"
        if run.status != expected_status:
            item.status = "canceled"
            item.completed_at = now
            item.revision += 1
            db.commit()
            continue
        node = next(node for node in version.definition["nodes"] if node["id"] == item.node_id)
        node_run = (
            db.query(WorkflowNodeRun)
            .filter_by(workflow_run_id=run.id, node_id=item.node_id, status="waiting")
            .order_by(WorkflowNodeRun.started_at.desc())
            .first()
        )
        item.status = "expired"
        item.completed_at = now
        item.revision += 1
        if node_run:
            node_run.status = "expired"
            node_run.finished_at = now
        if node.get("on_expire", "fail") == "expired":
            run.context = _node_output_context(item.resume_context, node["id"], {"decision": "expired"})
            run.status = "queued"
            run.current_node_id = _next_node(version.definition, node["id"], "expired")
        else:
            run.status = "timed_out"
            run.error = {"code": "INTERACTION_EXPIRED", "node_id": node["id"]}
            run.finished_at = now
        db.commit()
        expired += 1
    return expired
