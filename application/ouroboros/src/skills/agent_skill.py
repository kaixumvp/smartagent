import json

from src.plugins.base import InvokeContext
from src.skills.base import Skill


class AgentSkill(Skill):
    """An agent-skill invokes a sub-agent (parent-child nesting).

    `body.agent_ref` points at another Agent. The platform injects `run_subagent` at setup;
    it loads the sub-agent config, runs the same runtime graph, and returns the final answer.
    Recursion depth is capped by the runtime via `max_subagent_depth`.
    """

    type = "agent"

    async def invoke(self, ctx: InvokeContext, **kw) -> str:
        agent_ref = str(self._body.get("agent_ref", ""))
        if not agent_ref:
            return "agent skill is missing agent_ref"
        if self._run_subagent is None:
            return "sub-agent execution is not wired in this deployment"
        task = kw.get("task") or (json.dumps(kw, ensure_ascii=False) if kw else "")
        return await self._run_subagent(agent_ref, str(task), ctx)
