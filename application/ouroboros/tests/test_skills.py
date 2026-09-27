import pytest

from src.plugins.base import InvokeContext, PluginManifest
from src.skills.agent_skill import AgentSkill
from src.skills.base import build_skill
from src.skills.flow_skill import FlowSkill
from src.skills.function_skill import FunctionSkill
from src.skills.prompt_skill import PromptSkill


@pytest.mark.asyncio
async def test_prompt_skill_renders_placeholders():
    skill = PromptSkill(PluginManifest(name="greet", kind="skill"), {"template": "Hello {{name}}!"})
    out = await skill.invoke(InvokeContext(), name="World")
    assert out == "Hello World!"


@pytest.mark.asyncio
async def test_prompt_skill_renders_memory_ctx_placeholder():
    skill = PromptSkill(PluginManifest(name="p", kind="skill"), {"template": "ctx={{memory_ctx}}"})
    out = await skill.invoke(InvokeContext(), memory_ctx=[{"content": "偏好简洁"}])
    assert "偏好简洁" in out


@pytest.mark.asyncio
async def test_function_skill_runs():
    skill = FunctionSkill(
        PluginManifest(name="add", kind="skill"),
        {"source": "def run(**kw):\n    return str(int(kw['a']) + int(kw['b']))"},
    )
    out = await skill.invoke(InvokeContext(), a=1, b=2)
    assert out == "3"


@pytest.mark.asyncio
async def test_function_skill_missing_run_callable():
    skill = FunctionSkill(PluginManifest(name="bad", kind="skill"), {"source": "x = 1"})
    out = await skill.invoke(InvokeContext())
    assert "no run()" in out


@pytest.mark.asyncio
async def test_flow_skill_unwired_returns_notice():
    skill = FlowSkill(PluginManifest(name="report", kind="skill"), {"graph_spec": {}})
    out = await skill.invoke(InvokeContext())
    assert "not wired" in out


@pytest.mark.asyncio
async def test_flow_skill_wired_runs():
    async def fake_flow(graph_spec, ctx, kw):
        return "flow done"

    skill = FlowSkill(
        PluginManifest(name="report", kind="skill"),
        {"graph_spec": {"a": 1}},
        run_flow=fake_flow,
    )
    out = await skill.invoke(InvokeContext())
    assert out == "flow done"


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
    assert calls[0] == ("agent_x", "please help", 1)


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


def test_build_skill_dispatch():
    skill = build_skill("prompt", PluginManifest(name="s", kind="skill"), {"template": "hi"})
    assert isinstance(skill, PromptSkill)
    assert skill.type == "prompt"


def test_build_skill_unknown_type_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        build_skill("bogus", PluginManifest(name="s", kind="skill"), {})
