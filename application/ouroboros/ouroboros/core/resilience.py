"""Reliability primitives for the runtime (V0.3): exponential-backoff retry + circuit breaker.

Both are dependency-free and deterministic for tests (``base_delay=0`` disables backoff).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryPolicy(BaseModel):
    """Retry with exponential backoff: `max_retries` retries *after* the first attempt."""

    max_retries: int = 2
    base_delay: float = 0.5
    max_delay: float = 8.0

    def delay_for(self, attempt: int) -> float:
        """Backoff for the retry after the `attempt`-th failure (0-indexed)."""
        return min(self.max_delay, self.base_delay * (2 ** attempt))


class CircuitBreaker:
    """Trip open after `failure_threshold` consecutive failures; reset on a success.

    The host may share one breaker across runs to fail fast when a tool/LLM is persistently
    down. Time-based auto-reset is left to the host (e.g. schedule `reset()` on a timer).
    """

    def __init__(self, failure_threshold: int = 5) -> None:
        self._threshold = failure_threshold
        self._failures = 0

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1

    def reset(self) -> None:
        self._failures = 0

    @property
    def is_open(self) -> bool:
        return self._failures >= self._threshold

    @property
    def failures(self) -> int:
        return self._failures


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker refuses a call."""


async def run_with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    breaker: CircuitBreaker | None = None,
) -> T:
    """Call `fn`, retrying on exception with backoff; fail fast when the breaker is open.

    A `RetryPolicy(max_retries=0)` performs a single attempt with no retry. Each exception is
    recorded as a breaker failure; a success resets the breaker.
    """
    attempt = 0
    while True:
        if breaker is not None and breaker.is_open:
            raise CircuitOpenError("circuit breaker open")
        try:
            result = await fn()
        except Exception:  # noqa: BLE001 — retry any transient failure, then re-raise
            if breaker is not None:
                breaker.record_failure()
            if attempt >= policy.max_retries:
                raise
            delay = policy.delay_for(attempt)
            logger.warning(
                "transient failure, retrying in %.2fs (attempt %d/%d)",
                delay, attempt + 1, policy.max_retries, exc_info=True,
            )
            await asyncio.sleep(delay)
            attempt += 1
            continue
        if breaker is not None:
            breaker.record_success()
        return result
