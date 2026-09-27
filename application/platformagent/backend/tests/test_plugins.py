import pytest

from conftest import build_default_plugin_registry
from smartagent.iam.permission_manager import PermissionContext, PermissionManager
from src.core.nodes.execute import run_execute
from src.plugins.base import InvokeContext, PluginManifest
from src.plugins.manifest import format_ref, parse_ref
from src.plugins.registry import PluginRegistry
from src.skills.function_skill import FunctionSkill
from src.skills.prompt_skill import PromptSkill
from src.tools.base import ToolResult


def test_parse_ref():
    assert parse_ref("tool:calculator").name == "calculator"
    assert parse_ref("skill:refund@1.2.0").version == "1.2.0"
    assert parse_ref("skill:refund@1.2.0").kind == "skill"
    assert parse_ref("no-separator") is None


def test_format_ref():
    assert format_ref("skill", "refund", "1.2.0") == "skill:refund@1.2.0"
    assert format_ref("tool", "calculator") == "tool:calculator"


def test_function_name_namespacing():
    assert PluginManifest(name="refund", kind="skill").function_name == "skill_refund"
    assert PluginManifest(name="calculator", kind="tool").function_name == "calculator"


class _EchoTool:
    name = "echo"
    description = "echo a value"
    parameters = {"type": "object", "properties": {"x": {"type": "string"}}}
    permission = "read"

    async def run(self, **kw) -> ToolResult:
        return ToolResult(success=True, output=kw.get("x", ""))


@pytest.mark.asyncio
async def test_registry_openai_schema_and_invoke():
    registry = PluginRegistry()
    registry.register_tool(_EchoTool())

    schemas = registry.to_openai_schema()
    assert schemas[0]["function"]["name"] == "echo"

    result = await registry.invoke("echo", InvokeContext(), x="hi")
    assert isinstance(result, ToolResult)
    assert result.output == "hi"


@pytest.mark.asyncio
async def test_prompt_skill_renders_placeholders():
    skill = PromptSkill(PluginManifest(name="greet", kind="skill"), {"template": "Hello {{name}}!"})
    out = await skill.invoke(InvokeContext(), name="World")
    assert out == "Hello World!"


@pytest.mark.asyncio
async def test_function_skill_runs():
    skill = FunctionSkill(
        PluginManifest(name="add", kind="skill"),
        {"source": "def run(**kw):\n    return str(int(kw['a']) + int(kw['b']))"},
    )
    out = await skill.invoke(InvokeContext(), a=1, b=2)
    assert out == "3"


@pytest.mark.asyncio
async def test_execute_denies_without_run_permission():
    registry = build_default_plugin_registry()
    pm = PermissionManager()
    ctx = PermissionContext(is_admin=False, permission_codes=set(), grant_keys=set())
    state = {"action": "calculator", "action_input": {"expression": "1+1"}}

    result = await run_execute(state, registry, pm, ctx)
    assert "[denied]" in result["last_tool_result"]
