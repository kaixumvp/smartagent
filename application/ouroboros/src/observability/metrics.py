"""Metrics implementations (V0.4).

The ``Metrics`` protocol lives in ``ouroboros.ports``; hosts implement it to push counters /
histograms to Prometheus. The framework ships two reference implementations: ``NoopMetrics``
(default) and ``InMemoryMetrics`` (for tests / local introspection).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class NoopMetrics:
    """Discards all metrics — the default when the host doesn't inject one."""

    def incr(self, name: str, value: int = 1, labels: dict[str, str] | None = None) -> None:
        return None

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        return None


class InMemoryMetrics:
    """Collects metrics in-process for tests and local dashboards."""

    def __init__(self) -> None:
        self.counters: dict[Any, int] = defaultdict(int)
        self.observations: list[tuple[str, float, dict[str, str]]] = []

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> Any:
        return (name, tuple(sorted((labels or {}).items())))

    def incr(self, name: str, value: int = 1, labels: dict[str, str] | None = None) -> None:
        self.counters[self._key(name, labels)] += value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.observations.append((name, value, dict(labels or {})))


noop_metrics = NoopMetrics()

__all__ = ["NoopMetrics", "InMemoryMetrics", "noop_metrics"]
