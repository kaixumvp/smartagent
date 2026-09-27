"""Cost-aware LLM helpers (V1.1): prompt-cache reuse, tiered model routing, token budget."""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Callable

from src.ports import LLMResponse


class CachingGateway:
    """Memoize ``chat()`` by (model, messages, tools) — prompt-cache reuse across calls."""

    def __init__(self, gateway, max_size: int = 256) -> None:
        self._gateway = gateway
        self._max_size = max_size
        self._cache: OrderedDict[str, LLMResponse] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(messages, model, tools) -> str:
        return json.dumps({"model": model, "messages": messages, "tools": tools},
                          ensure_ascii=False, sort_keys=True, default=str)

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        key = self._key(messages, model, tools)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        resp = await self._gateway.chat(messages, model=model, tools=tools)
        self._cache[key] = resp
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return resp


class TokenBudget:
    """Track total token spend; ``consume`` returns False once the budget is exhausted."""

    def __init__(self, max_total_tokens: int) -> None:
        self._max = max_total_tokens
        self._used = 0

    def consume(self, usage) -> bool:
        self._used += (usage or {}).get("total_tokens", 0)
        return self._used <= self._max

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._used)

    @property
    def exhausted(self) -> bool:
        return self._used >= self._max


class TokenBudgetExceeded(RuntimeError):
    """Raised by the runtime when a run's token budget is exhausted."""


def message_length_classifier(threshold: int) -> Callable[[list[dict]], bool]:
    """Simple complexity heuristic: total message length above `threshold` → 'expensive'."""
    def classify(messages: list[dict]) -> bool:
        return sum(len(str(m.get("content", ""))) for m in messages) > threshold
    return classify


class TieredRouter:
    """Route simple tasks to a cheap model and complex ones to an expensive model.

    ``classifier(messages) -> bool`` returns True for 'complex' (use the expensive model).
    """

    def __init__(self, gateway, cheap_model: str, expensive_model: str, classifier) -> None:
        self._gateway = gateway
        self._cheap = cheap_model
        self._expensive = expensive_model
        self._classifier = classifier
        self.last_model: str | None = None

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        chosen = model or (self._expensive if self._classifier(messages) else self._cheap)
        self.last_model = chosen
        return await self._gateway.chat(messages, model=chosen, tools=tools)


__all__ = [
    "CachingGateway",
    "TokenBudget",
    "TokenBudgetExceeded",
    "TieredRouter",
    "message_length_classifier",
]
