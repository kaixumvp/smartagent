from abc import ABC, abstractmethod
from typing import Any

from src.plugins.base import InvokeContext, PluginManifest
from src.ports import FlowRunner, SubagentRunner

# Backward-compatible aliases (the canonical names now live in ouroboros.ports).
RunSubagent = SubagentRunner
RunFlow = FlowRunner


class Skill(ABC):
    """Base class for all skill forms. A Skill is a plugin with kind == "skill".

    The concrete form is carried by `type` (prompt | function | flow | agent) and dispatched
    by `build_skill`; `invoke` differs per form.
    """

    kind = "skill"
    type: str = ""

    def __init__(
        self,
        manifest: PluginManifest,
        body: dict,
        run_subagent: RunSubagent | None = None,
        run_flow: RunFlow | None = None,
    ) -> None:
        self._manifest = manifest
        self._body = body or {}
        self._run_subagent = run_subagent
        self._run_flow = run_flow

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    @property
    def body(self) -> dict:
        return self._body

    async def setup(self, config: dict) -> None:
        return None

    async def teardown(self) -> None:
        return None

    @abstractmethod
    async def invoke(self, ctx: InvokeContext, **kw: Any) -> str: ...


def build_skill(
    type_: str,
    manifest: PluginManifest,
    body: dict,
    run_subagent: RunSubagent | None = None,
    run_flow: RunFlow | None = None,
) -> Skill:
    """Instantiate the concrete skill class for a given form."""
    from src.skills.agent_skill import AgentSkill
    from src.skills.flow_skill import FlowSkill
    from src.skills.function_skill import FunctionSkill
    from src.skills.prompt_skill import PromptSkill

    cls: dict[str, type[Skill]] = {
        "prompt": PromptSkill,
        "function": FunctionSkill,
        "flow": FlowSkill,
        "agent": AgentSkill,
    }
    skill_cls = cls.get(type_)
    if skill_cls is None:
        raise ValueError(f"unknown skill type: {type_}")
    return skill_cls(manifest, body, run_subagent=run_subagent, run_flow=run_flow)
