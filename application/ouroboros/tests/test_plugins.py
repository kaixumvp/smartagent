import pytest

from src.plugins.base import InvokeContext, PluginManifest, ToolAsPlugin
from src.plugins.manifest import format_ref, parse_ref
from src.plugins.registry import PluginRegistry
from src.tools.base import ToolResult


def test_parse_ref():
    assert parse_ref("tool:calculator").name == "calculator"
    assert parse_ref("skill:refund@1.2.0").version == "1.2.0"
    assert parse_ref("skill:refund@1.2.0").kind == "skill"
    assert parse_ref("no-separator") is None
    assert parse_ref("") is None


def test_format_ref():
    assert format_ref("skill", "refund", "1.2.0") == "skill:refund@1.2.0"
    assert format_ref("tool", "calculator") == "tool:calculator"


def test_function_name_namespacing():
    assert PluginManifest(name="refund", kind="skill").function_name == "skill_refund"
    assert PluginManifest(name="calculator", kind="tool").function_name == "calculator"


class _EchoTool:
    id = "tool_echo"
    name = "echo"
    description = "echo a value"
    parameters = {"type": "object", "properties": {"x": {"type": "string"}}}
    permission = "read"

    async def run(self, x: str = "", **kw) -> ToolResult:
        return ToolResult(success=True, output=x)


def test_registry_register_and_index():
    registry = PluginRegistry()
    registry.register_tool(_EchoTool())
    assert registry.get("echo") is not None
    assert registry.get("tool:echo") is not None
    assert registry.get("tool_echo") is None  # id is not indexed; only name/ref/function_name


@pytest.mark.asyncio
async def test_registry_openai_schema_and_invoke():
    registry = PluginRegistry()
    registry.register_tool(_EchoTool())

    schemas = registry.to_openai_schema()
    assert schemas[0]["function"]["name"] == "echo"

    result = await registry.invoke("echo", InvokeContext(), x="hi")
    assert isinstance(result, ToolResult)
    assert result.output == "hi"


def test_tool_as_plugin_adapts_manifest():
    plugin = ToolAsPlugin(_EchoTool())
    assert plugin.kind == "tool"
    assert plugin.manifest.name == "echo"
    assert plugin.manifest.kind == "tool"
    assert plugin.manifest.permission == "read"


def test_parse_ref_unknown_kind_still_parses():
    ref = parse_ref("knowledge:docs_rag@2")
    assert ref is not None and ref.kind == "knowledge" and ref.name == "docs_rag"
