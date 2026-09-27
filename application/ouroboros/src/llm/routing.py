"""LLM routing and fault tolerance (V0.4).

``FallbackLLMGateway`` tries a list of ``LLMGateway``s in order and fails over to the next
on error. ``FaultTolerantGateway`` decorates a gateway so a malformed or failing response
degrades to a valid empty ``LLMResponse`` instead of raising — structured-output fallback.
Both are plain ``LLMGateway`` implementations, so they compose with anything.
"""

from __future__ import annotations

import logging

from src.ports import LLMGateway, LLMResponse, Usage

logger = logging.getLogger(__name__)


class FallbackLLMGateway:
    """Route across vendors with failover. `last_used` records which gateway served the last call."""

    def __init__(self, gateways: list[LLMGateway]) -> None:
        if not gateways:
            raise ValueError("FallbackLLMGateway requires at least one gateway")
        self._gateways = gateways
        self.last_used: str | None = None

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        last_exc: Exception | None = None
        for gateway in self._gateways:
            try:
                resp = await gateway.chat(messages, model=model, tools=tools)
                self.last_used = getattr(gateway, "_model", None) or type(gateway).__name__
                return resp
            except Exception as exc:  # noqa: BLE001 — failover on any vendor error
                last_exc = exc
                logger.warning("gateway %s failed, falling back: %s", type(gateway).__name__, exc)
        raise RuntimeError("all LLM gateways failed") from last_exc


class FaultTolerantGateway:
    """Catch gateway errors / malformed tool-calls and return a valid empty response."""

    def __init__(self, gateway: LLMGateway, *, on_error: str = "") -> None:
        self._gateway = gateway
        self._on_error = on_error

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        try:
            resp = await self._gateway.chat(messages, model=model, tools=tools)
        except Exception as exc:  # noqa: BLE001 — structured-output fallback
            logger.warning("gateway error, falling back to empty response: %s", exc)
            return LLMResponse(content=self._on_error, usage=Usage())
        # Tolerate a response whose tool_calls were not parsed (None) by normalizing to [].
        if getattr(resp, "tool_calls", None) is None:
            resp.tool_calls = []
        return resp


__all__ = ["FallbackLLMGateway", "FaultTolerantGateway"]
