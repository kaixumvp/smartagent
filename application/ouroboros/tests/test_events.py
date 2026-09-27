from src.events import (
    RuntimeEvent,
    run_approved,
    run_awaiting_human,
    run_completed,
    run_failed,
    run_rejected,
    run_started,
    step_completed,
)


def test_runtime_event_defaults():
    e = RuntimeEvent(event="run.started")
    assert e.event == "run.started"
    assert e.data == {}
    assert e.run_id is None


def test_run_started():
    e = run_started("r1")
    assert e.event == "run.started"
    assert e.run_id == "r1"
    assert e.data["run_id"] == "r1"
    assert e.data["status"] == "running"


def test_step_completed():
    e = step_completed({"run_id": "r1", "seq": 3, "node": "execute", "action": "calculator", "output": {"result": "124"}, "latency_ms": 10})
    assert e.event == "step.completed"
    assert e.run_id == "r1"
    assert e.data["seq"] == 3
    assert e.data["node"] == "execute"


def test_step_completed_accepts_model():
    from src.core.runtime import Step

    e = step_completed(Step(seq=1, node="plan", run_id="r1"))
    assert e.data["node"] == "plan"
    assert e.data["seq"] == 1


def test_run_completed():
    e = run_completed("r1", "124", {"total_tokens": 100})
    assert e.event == "run.completed"
    assert e.data["status"] == "completed"
    assert e.data["usage"]["total_tokens"] == 100


def test_run_failed():
    e = run_failed("r1", "boom")
    assert e.event == "run.failed"
    assert e.data["status"] == "failed"
    assert e.data["error"] == "boom"


def test_run_awaiting_human():
    e = run_awaiting_human("r1", [{"resource_type": "tool", "resource_id": "x"}])
    assert e.event == "run.awaiting_human"
    assert e.data["status"] == "awaiting_human"
    assert e.data["pending_approvals"][0]["resource_id"] == "x"


def test_run_approved():
    e = run_approved("r1")
    assert e.event == "run.approved"
    assert e.data["status"] == "running"


def test_run_rejected():
    e = run_rejected("r1")
    assert e.event == "run.rejected"
    assert e.data["status"] == "canceled"
