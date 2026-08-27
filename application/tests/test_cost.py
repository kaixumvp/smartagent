"""Cost accounting and tiered routing (V1.1).

The routing tests exist because of a contract trap: `AgentRuntime` forwards
`definition.model` to every node, so anything that only routes when the model is absent would
silently never route. These pin the behaviour that fix depends on.
"""

import pytest

from conftest import MockLLMGateway
from smartagent.adapters.cost_gateway import RunScopedRoutingGateway
from smartagent.pricing import estimate_cost
from ouroboros.llm.base import LLMResponse, Usage


class RecordingGateway:
    """Inner gateway that remembers the model it was asked for."""

    def __init__(self) -> None:
        self.models: list[str | None] = []

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        self.models.append(model)
        return LLMResponse(
            content="ok", usage=Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        )


def _gateway(inner, **kw) -> RunScopedRoutingGateway:
    defaults = dict(
        default_model="default-model",
        routing_enabled=True,
        cheap_model="cheap",
        expensive_model="expensive",
        threshold=100,
    )
    defaults.update(kw)
    return RunScopedRoutingGateway(inner, **defaults)


def _short() -> list[dict]:
    return [{"role": "user", "content": "hi"}]


def _long() -> list[dict]:
    return [{"role": "user", "content": "x" * 500}]


# --------------------------------------------------------------------------- pricing
def test_estimate_cost_uses_per_direction_prices():
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    # deepseek-chat: 0.00027/1K in, 0.0011/1K out
    assert estimate_cost("deepseek-chat", usage) == pytest.approx(0.00027 + 0.00055)


def test_estimate_cost_falls_back_to_prefix_match():
    usage = {"prompt_tokens": 1000, "completion_tokens": 0}
    assert estimate_cost("gpt-4o-2024-08-06", usage) == estimate_cost("gpt-4o", usage)


def test_estimate_cost_is_zero_for_unknown_model():
    """A missing price reports 0 rather than raising — cost accounting must not fail a run."""
    assert estimate_cost("no-such-model", {"prompt_tokens": 10_000}) == 0.0
    assert estimate_cost(None, {"prompt_tokens": 10_000}) == 0.0


def test_estimate_cost_honours_overrides():
    usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
    cost = estimate_cost("house-model", usage, overrides={"house-model": [1.0, 2.0]})
    assert cost == pytest.approx(3.0)


# --------------------------------------------------------------------------- routing
@pytest.mark.asyncio
async def test_pinned_model_wins_over_routing():
    """An agent that set `config.model` keeps it; routing is only for agents that did not."""
    inner = RecordingGateway()
    gateway = _gateway(inner)

    await gateway.chat(_long(), model="pinned-model")

    assert inner.models == ["pinned-model"]
    assert gateway.model == "pinned-model"


@pytest.mark.asyncio
async def test_routing_picks_tier_by_complexity():
    inner = RecordingGateway()
    gateway = _gateway(inner)

    await gateway.chat(_short(), model="")   # build_definition emits "" for an unpinned agent
    await gateway.chat(_long(), model="")

    assert inner.models == ["cheap", "expensive"]


@pytest.mark.asyncio
async def test_routing_disabled_uses_default_model():
    inner = RecordingGateway()
    gateway = _gateway(inner, routing_enabled=False)

    await gateway.chat(_long(), model="")

    assert inner.models == ["default-model"]


@pytest.mark.asyncio
async def test_inner_gateway_always_receives_a_concrete_model():
    """The cache sits below this gateway and keys on the model. If an empty model reached it,
    every routed call would collide on one key and cross-contaminate the tiers."""
    inner = RecordingGateway()
    gateway = _gateway(inner)

    await gateway.chat(_short(), model="")
    await gateway.chat(_long(), model="")
    await gateway.chat(_short(), model="pinned")

    assert all(m for m in inner.models), inner.models
    assert len(set(inner.models)) == 3


# --------------------------------------------------------------------------- attribution
@pytest.mark.asyncio
async def test_cost_is_summed_per_call_with_the_serving_model():
    inner = RecordingGateway()
    gateway = _gateway(
        inner, cheap_model="cheap", expensive_model="expensive",
    )
    gateway._price_overrides = {"cheap": [0.001, 0.002], "expensive": [0.01, 0.02]}

    await gateway.chat(_short(), model="")  # cheap:     1.0*0.001 + 0.5*0.002 = 0.002
    await gateway.chat(_long(), model="")   # expensive: 1.0*0.01  + 0.5*0.02  = 0.02

    assert gateway.cost == pytest.approx(0.022)
    assert gateway.model == "expensive"  # last model used; cost stays exact per call


@pytest.mark.asyncio
async def test_ledger_is_per_instance():
    """Attribution lives on a per-run object, not a shared attribute — concurrent evaluation
    cases would otherwise overwrite each other's model/cost."""
    a, b = _gateway(RecordingGateway()), _gateway(RecordingGateway())

    await a.chat(_short(), model="model-a")

    assert a.model == "model-a"
    assert b.model is None
    assert b.cost == 0.0


@pytest.mark.asyncio
async def test_gateway_passes_tools_through():
    llm = MockLLMGateway([LLMResponse(content="ok", usage=Usage())])
    gateway = _gateway(llm, routing_enabled=False)

    await gateway.chat(_short(), model="m", tools=[{"type": "function"}])

    assert llm.calls[0]["tools"] == [{"type": "function"}]


# --------------------------------------------------------------------------- through the runtime
@pytest.mark.asyncio
async def test_routing_and_cost_survive_a_real_run():
    """The unit tests above cannot catch the original trap on their own.

    `AgentRuntime` reads `definition.model` once and hands it to every node, so a router that
    defers to the caller's model would look fine in isolation and never route in production.
    This drives an actual run and asserts both halves: the tier was chosen, and the cost landed
    on the run row.
    """
    from conftest import FakeMemoryManager, FakeSession, admin_permission_context, admin_principal
    from smartagent.config import Settings
    from smartagent.db.models import Agent, Run
    from smartagent.iam.permission_manager import PermissionManager
    from smartagent.services.run_service import RunService
    from smartagent.util import new_id
    from ouroboros.tools.registry import build_default_registry

    class Gateway:
        def __init__(self):
            self.models = []

        async def chat(self, messages, model=None, tools=None):
            self.models.append(model)
            return LLMResponse(
                content="done",
                usage=Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
            )

    agent = Agent(
        id="agent_test", tenant_id="default", name="t", version="1",
        config={}, status="active", is_latest=True,  # no config.model → unpinned → routed
    )
    db = FakeSession(agent)
    gateway = Gateway()
    settings = Settings(
        llm_routing_enabled=True,
        llm_cheap_model="deepseek-chat",
        llm_expensive_model="gpt-4o",
        llm_routing_threshold=10,
    )
    service = RunService(
        db=db,
        llm=gateway,
        memory=FakeMemoryManager(),
        settings=settings,
        principal=admin_principal(),
        permission_context=admin_permission_context(),
        permission_manager=PermissionManager(),
        tool_registry=build_default_registry(),
    )
    run = Run(id=new_id("run"), agent_id=agent.id, tenant_id="default", input="x" * 200, status="running")
    db.add(run)

    registry = await service.load_registry(db, agent)
    result = await service.start(agent, run, task="x" * 200, user_id="u_1", registry=registry)
    await service.finalize(agent, run, result, user_id="u_1")

    assert gateway.models and all(m == "gpt-4o" for m in gateway.models), gateway.models
    assert run.model == "gpt-4o"
    # gpt-4o is (0.0025 in, 0.01 out) per 1K → 0.0075 a call, over two calls.
    assert run.cost == pytest.approx(0.0075 * len(gateway.models))
