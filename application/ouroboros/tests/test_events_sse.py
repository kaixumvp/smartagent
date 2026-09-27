import warnings


def test_sse_shim_serialize_and_factories():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from src.events.sse import SSEEvent, run_completed, run_started

    e = SSEEvent(event="run.started", data={"run_id": "r1", "status": "running"})
    assert e.serialize() == 'event: run.started\ndata: {"run_id": "r1", "status": "running"}\n\n'

    # Factories are re-exported and remain usable during the deprecation window.
    assert run_started("r1").event == "run.started"
    assert run_completed("r1", "x", {}).data["status"] == "completed"
