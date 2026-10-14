import pytest

from smartagent.adapters import db_plugin_loader
from smartagent.adapters.db_plugin_loader import PluginLoader
from ouroboros.tools.registry import ToolRegistry


class FakeCapabilityClient:
    def __init__(self, base_url, integration_key) -> None:
        self.calls = []

    async def list_providers(self):
        return [{"id": "11111111-1111-4111-8111-111111111111", "name": "weather-service"}]

    async def list_provider_tools(self, provider_id):
        return [
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "name": "forecast",
                "display_name": "天气预报",
                "description": "按城市查询天气",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "name": "air_quality",
                "display_name": "空气质量",
                "description": "按城市查询空气质量",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    async def list_tools(self):
        return [
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "source": "api",
                "service_name": "weather-api",
                "name": "get_weather",
                "display_name": "查询天气",
                "description": "按城市查询天气",
                "permission": "write",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ]

    async def call_tool(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        return {"content": [{"type": "text", "text": "sunny"}]}


def make_loader(monkeypatch):
    monkeypatch.setattr(db_plugin_loader, "CapabilityRegistryClient", FakeCapabilityClient)
    return PluginLoader(ToolRegistry(), object(), "http://registry.test", "test-key")


@pytest.mark.asyncio
async def test_provider_reference_registers_all_tools(monkeypatch):
    loader = make_loader(monkeypatch)
    registry = await loader.load_for_agent(
        None,
        "tenant",
        {
            "plugins": [
                {
                    "type": "capability_provider",
                    "ref": "11111111-1111-4111-8111-111111111111",
                }
            ]
        },
    )

    manifests = [plugin.manifest for plugin in registry.all()]
    assert len(manifests) == 2
    assert {manifest.name for manifest in manifests} == {
        "mcp_weather_serv_forecast_22222222",
        "mcp_weather_serv_air_quality_33333333",
    }
    assert next(m for m in manifests if m.name.endswith("22222222")).parameters["required"] == ["city"]


@pytest.mark.asyncio
async def test_tool_reference_registers_only_selected_tool_and_invokes_via_registry(monkeypatch):
    loader = make_loader(monkeypatch)
    registry = await loader.load_for_agent(
        None,
        "tenant",
        {
            "plugins": [
                {
                    "type": "capability_tool",
                    "ref": "11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222",
                }
            ]
        },
    )

    plugins = registry.all()
    assert len(plugins) == 1
    assert plugins[0].manifest.description.startswith("天气预报:")

    result = await plugins[0].invoke(None, city="杭州")
    assert result.success
    assert result.output["content"][0]["text"] == "sunny"
    assert plugins[0]._tool._client.calls == [
        ("22222222-2222-4222-8222-222222222222", {"city": "杭州"})
    ]


@pytest.mark.asyncio
async def test_invalid_capability_reference_fails_explicitly(monkeypatch):
    loader = make_loader(monkeypatch)
    with pytest.raises(ValueError, match="valid provider and tool IDs"):
        await loader.load_for_agent(
            None,
            "tenant",
            {"plugins": [{"type": "capability_provider", "ref": "not-a-uuid"}]},
        )


@pytest.mark.asyncio
async def test_api_tool_reference_registers_standard_tool_and_calls_capability(monkeypatch):
    loader = make_loader(monkeypatch)
    registry = await loader.load_for_agent(
        None,
        "tenant",
        {
            "plugins": [
                {
                    "type": "capability_api_tool",
                    "ref": "44444444-4444-4444-8444-444444444444",
                }
            ]
        },
    )

    plugins = registry.all()
    assert len(plugins) == 1
    assert plugins[0].manifest.name == "api_weather_api_get_weather_44444444"
    assert plugins[0].manifest.parameters["required"] == ["city"]
    assert plugins[0]._tool.permission == "write"

    result = await plugins[0].invoke(None, city="Hangzhou")
    assert result.success
    assert result.output["content"][0]["text"] == "sunny"
    assert plugins[0]._tool._client.calls == [
        ("44444444-4444-4444-8444-444444444444", {"city": "Hangzhou"})
    ]
