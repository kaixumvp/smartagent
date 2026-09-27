import logging
from typing import Any

from src.plugins.base import InvokeContext, Plugin, ToolAsPlugin
from src.plugins.manifest import format_ref

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Holds the plugins an Agent is assembled from and resolves them by key or function name.

    A plugin is indexed three ways: by bare name, by full `kind:name@version` ref, and by the
    OpenAI function name exposed to the LLM (see PluginManifest.function_name). Resolution
    therefore accepts any of these forms.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, Plugin] = {}
        self._by_fn: dict[str, str] = {}  # function_name -> primary key

    def register(self, plugin: Plugin) -> None:
        manifest = plugin.manifest
        logger.debug("register plugin: %s", manifest.function_name)
        # Bare name is the primary key for a single-agent registry (one version per plugin).
        self._by_key[manifest.name] = plugin
        self._by_key[format_ref(manifest.kind, manifest.name, manifest.version)] = plugin
        self._by_key[format_ref(manifest.kind, manifest.name)] = plugin
        self._by_fn[manifest.function_name] = manifest.name

    def register_tool(self, tool: Any) -> None:
        """Wrap a legacy V0.1 Tool and register it as a plugin."""
        self.register(ToolAsPlugin(tool))

    def _resolve_key(self, key: str) -> str | None:
        if key in self._by_key:
            return key
        if key in self._by_fn:
            return self._by_fn[key]
        return None

    def get(self, key: str) -> Plugin | None:
        resolved = self._resolve_key(key)
        return self._by_key.get(resolved) if resolved else None

    def all(self) -> list[Plugin]:
        seen: set[int] = set()
        plugins: list[Plugin] = []
        for plugin in self._by_key.values():
            if id(plugin) not in seen:
                seen.add(id(plugin))
                plugins.append(plugin)
        return plugins

    def resolve(self, keys: list[str] | None = None) -> list[Plugin]:
        """Resolve a list of keys into plugin objects; None means all registered plugins."""
        if keys is None:
            return self.all()
        seen: set[int] = set()
        plugins: list[Plugin] = []
        for key in keys:
            plugin = self.get(key)
            if plugin is not None and id(plugin) not in seen:
                seen.add(id(plugin))
                plugins.append(plugin)
        return plugins

    def to_openai_schema(self, keys: list[str] | None = None) -> list[dict]:
        """Build OpenAI function-calling schemas for the resolved plugins."""
        schemas: list[dict] = []
        for plugin in self.resolve(keys):
            m = plugin.manifest
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": m.function_name,
                        "description": m.description,
                        "parameters": m.parameters,
                    },
                }
            )
        return schemas

    async def invoke(self, key: str, ctx: InvokeContext, **kw: Any) -> Any:
        """Invoke a plugin by key or function name. Raises KeyError when unknown."""
        plugin = self.get(key)
        if plugin is None:
            raise KeyError(f"unknown plugin: {key}")
        return await plugin.invoke(ctx, **kw)

    async def run(self, name: str, **kw: Any) -> Any:
        """Backward-compatible alias that invokes a plugin by its bare name."""
        return await self.invoke(name, InvokeContext(), **kw)
