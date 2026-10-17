import uuid
from unittest.mock import Mock

import pytest

from app.workflow_engine import (
    _evaluate,
    _execute_from,
    _read_path,
    _validate_json_value,
    validate_definition,
)
from app.models import WorkflowRun, WorkflowVersion


def _db():
    return Mock()


def test_validate_linear_workflow():
    definition = {
        "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
        "edges": [{"from": "start", "to": "end"}],
    }

    validate_definition(_db(), definition)


def test_validate_rejects_cycles_and_unreachable_nodes():
    definition = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "step", "type": "transform", "output_mapping": {}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "step"},
            {"from": "step", "to": "start"},
        ],
    }

    with pytest.raises(ValueError, match="acyclic"):
        validate_definition(_db(), definition)


def test_validate_approval_requires_explicit_decision_edges():
    definition = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "approval", "type": "approval"},
            {"id": "yes", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "approval"},
            {"from": "approval", "to": "yes", "branch": "approved"},
        ],
    }

    with pytest.raises(ValueError, match="requires approved and rejected"):
        validate_definition(_db(), definition)


def test_condition_evaluation_and_safe_paths():
    context = {
        "input": {"amount": 12},
        "workflow": {},
        "node": {"lookup": {"output": {"status": "ready"}}},
    }

    assert _read_path(context, "$.node.lookup.output.status") == "ready"
    assert _evaluate(
        {"op": "and", "args": [
            {"op": "gte", "left": "$.input.amount", "right": 10},
            {"op": "equals", "left": "$.node.lookup.output.status", "right": "ready"},
        ]},
        context,
    )
    with pytest.raises(ValueError, match="Unsupported context path"):
        _read_path(context, "$.secret.value")


def test_schema_validation_checks_required_fields_and_types():
    schema = {
        "type": "object",
        "properties": {"quantity": {"type": "integer"}},
        "required": ["quantity"],
        "additionalProperties": False,
    }

    with pytest.raises(ValueError, match="required"):
        _validate_json_value({}, schema)
    with pytest.raises(ValueError, match="expected integer"):
        _validate_json_value({"quantity": "one"}, schema)
    _validate_json_value({"quantity": 1}, schema)


def test_executor_persists_node_outputs_into_run_context():
    class SessionStub:
        def __init__(self, run):
            self.run = run
            self.items = []

        def add(self, item):
            if getattr(item, "id", None) is None:
                item.id = uuid.uuid4()
            self.items.append(item)

        def commit(self):
            return None

        def rollback(self):
            return None

        def get(self, model, item_id):
            return self.run if model is WorkflowRun and item_id == self.run.id else None

    definition = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "normalize", "type": "transform", "output_mapping": {"amount": "$.input.amount"}},
            {"id": "end", "type": "end", "output_mapping": {"amount": "$.node.normalize.output.amount"}},
        ],
        "edges": [
            {"from": "start", "to": "normalize"},
            {"from": "normalize", "to": "end"},
        ],
        "output_schema": {"type": "object", "properties": {"amount": {"type": "integer"}}},
    }
    run = WorkflowRun(
        id=uuid.uuid4(),
        status="running",
        context={"input": {"amount": 7}, "workflow": {}, "node": {}},
    )
    version = WorkflowVersion(definition=definition)

    result = _execute_from(SessionStub(run), run, version, "start")

    assert result["status"] == "succeeded"
    assert result["output"] == {"amount": 7}
    assert run.context["node"]["normalize"]["output"] == {"amount": 7}
