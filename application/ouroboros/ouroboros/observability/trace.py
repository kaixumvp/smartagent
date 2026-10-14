"""OpenTelemetry tracing (V0.4) — optional dependency, no-op fallback.

The framework depends only on ``opentelemetry-api`` and treats it as optional: when it is not
installed, ``Tracer`` degrades to no-ops, so ``pip install ouroboros`` still works offline.
The host injects a ``Tracer`` (or accepts the module default) via ``RuntimeDeps.tracer``.
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator

try:  # pragma: no cover - exercised only when opentelemetry-api is installed
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import StatusCode as _StatusCode

    _HAS_OTEL = True
except ImportError:  # pragma: no cover
    _otel_trace = None
    _StatusCode = None
    _HAS_OTEL = False


class Tracer:
    """Thin wrapper around an OTel tracer; every method is a no-op without OTel installed."""

    def __init__(self, name: str = "ouroboros", enabled: bool = True) -> None:
        self._name = name
        self._enabled = bool(enabled and _HAS_OTEL)
        self._tracer = _otel_trace.get_tracer(name) if self._enabled else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @contextlib.contextmanager
    def start_span(
        self, name: str, *, attributes: dict[str, Any] | None = None
    ) -> Iterator[Any]:
        """Context manager producing a child span; yields ``None`` when tracing is off."""
        if not self._enabled:
            yield None
            return
        with self._tracer.start_as_current_span(name, attributes=attributes or None) as span:
            yield span

    def current_trace_id(self) -> str | None:
        """Hex trace id of the currently-active span (32 chars), or None when tracing is off."""
        if not self._enabled:
            return None
        ctx = _otel_trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx.is_valid else None

    def record_error(self, span: Any, exc: BaseException) -> None:
        """Mark `span` failed and attach the exception (no-op if span is None)."""
        if span is not None and self._enabled:
            span.record_exception(exc)
            span.set_status(_StatusCode.ERROR)


default_tracer = Tracer()


def get_tracer(name: str = "ouroboros") -> Tracer:
    return Tracer(name)


__all__ = ["Tracer", "get_tracer", "default_tracer"]
