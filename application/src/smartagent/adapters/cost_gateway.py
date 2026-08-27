"""Per-run LLM gateway: tier selection plus cost attribution (business adapter).

**Why not the framework's `TieredRouter`** (`ouroboros/llm/cost.py:75`) — two reasons, both
load-bearing:

1. It only picks a tier when the caller supplies no model (`chosen = model or ...`,
   `cost.py:89`). But `AgentRuntime` reads `definition.model` once (`runtime.py:249`) and
   passes it to every node (`plan.py:54`, `decide.py:36`), so a concrete model always arrives
   and the tier branch is dead. Dropped in behind the runtime, it would never route.
2. It records the chosen model on `last_model`, a plain attribute of a shared instance
   (`cost.py:86`). Evaluations run cases concurrently against one gateway, so that attribute
   races and cannot attribute cost to a run.

This gateway is built per run, so its ledger has no contention, and an agent that pinned a
model in `agent.config.model` keeps it — routing only decides for agents that did not.
"""

import logging

from smartagent.pricing import estimate_cost
from ouroboros.llm.cost import message_length_classifier

logger = logging.getLogger(__name__)


class RunScopedRoutingGateway:
    """Wraps the shared gateway for the lifetime of a single run.

    The incoming `model` argument doubles as the opt-out: `build_definition` emits the agent's
    configured model, or `""` when it has none. Truthy → the agent pinned it, pass it through.
    Falsy → this gateway decides.
    """

    def __init__(
        self,
        inner,
        *,
        default_model: str,
        routing_enabled: bool = False,
        cheap_model: str = "",
        expensive_model: str = "",
        threshold: int = 2000,
        price_overrides: dict[str, list[float]] | None = None,
    ) -> None:
        self._inner = inner
        self._default_model = default_model
        self._routing_enabled = routing_enabled and bool(cheap_model) and bool(expensive_model)
        self._cheap = cheap_model
        self._expensive = expensive_model
        self._classifier = message_length_classifier(threshold)
        self._price_overrides = price_overrides
        # (model, usage) per call — the run's private cost ledger.
        self.calls: list[tuple[str, dict]] = []

    async def chat(self, messages, model=None, tools=None):
        chosen = self._resolve(messages, model)
        resp = await self._inner.chat(messages, model=chosen, tools=tools)
        usage = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage or {})
        self.calls.append((chosen, usage))
        return resp

    def _resolve(self, messages: list[dict], model: str | None) -> str:
        if model:
            return model  # the agent pinned this model in its config — respect it
        if self._routing_enabled:
            return self._expensive if self._classifier(messages) else self._cheap
        return self._default_model

    @property
    def model(self) -> str | None:
        """Model recorded on the run. With mixed tiers this is the last one used; `cost` stays
        exact regardless, since every call is priced against the model that served it."""
        return self.calls[-1][0] if self.calls else None

    @property
    def cost(self) -> float:
        return round(
            sum(estimate_cost(m, u, overrides=self._price_overrides) for m, u in self.calls), 6
        )


__all__ = ["RunScopedRoutingGateway"]
