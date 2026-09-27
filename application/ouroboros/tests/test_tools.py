import pytest

from src.tools.base import ToolResult
from src.tools.builtin.calculator import CalculatorTool
from src.tools.http_openapi import build_url_template, load_spec, operation_to_json_schema
from src.tools.registry import ToolRegistry, build_default_registry


@pytest.mark.asyncio
async def test_calculator_evaluates_expression():
    tool = CalculatorTool()
    r = await tool.run(expression="3*8+100")
    assert r.success
    assert r.output == "124"


@pytest.mark.asyncio
async def test_calculator_rejects_injection():
    tool = CalculatorTool()
    r = await tool.run(expression="__import__('os')")
    assert not r.success


@pytest.mark.asyncio
async def test_calculator_rejects_division_by_zero():
    tool = CalculatorTool()
    r = await tool.run(expression="1/0")
    assert not r.success


class _EchoTool:
    id = "tool_echo"
    name = "echo"
    description = "echo"
    permission = "read"
    parameters = {"type": "object", "properties": {"x": {"type": "string"}}}

    async def run(self, x: str = "", **kw) -> ToolResult:
        return ToolResult(success=True, output=x)


def test_tool_registry_indexes_by_name_and_id():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    assert reg.get("echo") is not None
    assert reg.get("tool_echo") is not None
    assert reg.all()  # deduped


def test_build_default_registry_has_builtins():
    reg = build_default_registry()
    names = {t.name for t in reg.all()}
    assert {"calculator", "http"} <= names


@pytest.mark.asyncio
async def test_tool_registry_run():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    r = await reg.run("echo", x="hi")
    assert r.output == "hi"


@pytest.mark.asyncio
async def test_tool_registry_unknown_tool():
    reg = ToolRegistry()
    r = await reg.run("nope")
    assert not r.success
    assert "unknown tool" in r.error


def test_load_spec_json():
    spec = load_spec('{"openapi": "3.0.0", "paths": {}}')
    assert spec["openapi"] == "3.0.0"


def test_build_url_template_joins_base_and_path():
    url = build_url_template([{"url": "https://api.example.com/v1/"}], "/orders/{order_id}")
    assert url == "https://api.example.com/v1/orders/{order_id}"


def test_operation_to_json_schema_params_and_body():
    op = {
        "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
            {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
        ],
        "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
    }
    schema = operation_to_json_schema(op)
    assert schema["required"] == ["id"]
    assert set(schema["properties"]) == {"id", "verbose", "body"}
