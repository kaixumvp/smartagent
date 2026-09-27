import pytest

from ouroboros.plugins.base import InvokeContext, PluginManifest
from ouroboros.skills.agent_skill import AgentSkill


@pytest.mark.asyncio
async def test_agent_skill_dispatches_to_run_subagent():
    calls: list = []

    async def fake_sub(agent_ref, task, ctx):
        calls.append((agent_ref, task, ctx.subagent_depth))
        return "sub result"

    skill = AgentSkill(
        PluginManifest(name="escalate", kind="skill"),
        {"agent_ref": "agent_x"},
        run_subagent=fake_sub,
    )
    out = await skill.invoke(InvokeContext(subagent_depth=1), task="please help")
    assert out == "sub result"
    assert calls[0][0] == "agent_x"
    assert calls[0][2] == 1


@pytest.mark.asyncio
async def test_agent_skill_missing_agent_ref():
    skill = AgentSkill(PluginManifest(name="escalate", kind="skill"), {})
    out = await skill.invoke(InvokeContext())
    assert "missing agent_ref" in out


@pytest.mark.asyncio
async def test_agent_skill_unwired_returns_notice():
    skill = AgentSkill(PluginManifest(name="escalate", kind="skill"), {"agent_ref": "agent_x"})
    out = await skill.invoke(InvokeContext())
    assert "not wired" in out
