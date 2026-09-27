from src.plugins.base import InvokeContext
from src.skills.base import Skill


class FlowSkill(Skill):
    """A flow-skill is a predefined multi-step subgraph (`body.graph_spec`).

    Executing an arbitrary serialized LangGraph spec is deferred: V0.2 only supports flows that
    the platform has registered a `run_flow` executor for (injected at setup). When none is
    wired, invoking the skill returns an explicit notice rather than failing silently.
    """

    type = "flow"

    async def invoke(self, ctx: InvokeContext, **kw) -> str:
        if self._run_flow is None:
            return "flow skill execution is not wired in this deployment (V0.2)"
        return await self._run_flow(self._body.get("graph_spec", {}), ctx, kw)
