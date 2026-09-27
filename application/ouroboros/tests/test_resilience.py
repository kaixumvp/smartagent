import pytest

from src.core.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    run_with_retry,
)


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    result = await run_with_retry(flaky, policy=RetryPolicy(max_retries=3, base_delay=0))
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_raises():
    async def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_with_retry(always_fail, policy=RetryPolicy(max_retries=2, base_delay=0))


@pytest.mark.asyncio
async def test_no_retry_when_max_retries_zero():
    calls = {"n": 0}

    async def fail():
        calls["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_with_retry(fail, policy=RetryPolicy(max_retries=0, base_delay=0))
    assert calls["n"] == 1


def test_retry_backoff_caps_at_max_delay():
    policy = RetryPolicy(base_delay=0.5, max_delay=2.0)
    assert policy.delay_for(0) == 0.5
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(3) == 2.0  # 4.0 capped at 2.0


def test_circuit_breaker_opens_and_resets():
    b = CircuitBreaker(failure_threshold=3)
    b.record_failure()
    b.record_failure()
    assert not b.is_open
    b.record_failure()
    assert b.is_open
    b.record_success()
    assert not b.is_open


def test_circuit_breaker_explicit_reset():
    b = CircuitBreaker(failure_threshold=1)
    b.record_failure()
    assert b.is_open
    b.reset()
    assert not b.is_open
    assert b.failures == 0


@pytest.mark.asyncio
async def test_circuit_breaker_short_circuits():
    b = CircuitBreaker(failure_threshold=1)

    async def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_with_retry(fail, policy=RetryPolicy(max_retries=0, base_delay=0), breaker=b)
    assert b.is_open
    with pytest.raises(CircuitOpenError):
        await run_with_retry(fail, policy=RetryPolicy(max_retries=0, base_delay=0), breaker=b)
