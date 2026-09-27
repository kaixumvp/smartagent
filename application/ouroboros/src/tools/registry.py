import logging

from src.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Register tools indexed by both name and id; provide OpenAI function-calling JSON Schema conversion."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        logger.debug("register tool: %s", tool.name)
        self._tools[tool.name] = tool
        tool_id = getattr(tool, "id", None)
        if tool_id:
            self._tools[tool_id] = tool

    def get(self, key: str) -> Tool | None:
        return self._tools.get(key)

    def all(self) -> list[Tool]:
        seen: set[int] = set()
        tools: list[Tool] = []
        for t in self._tools.values():
            if id(t) not in seen:
                seen.add(id(t))
                tools.append(t)
        return tools

    def resolve(self, keys: list[str] | None) -> list[Tool]:
        """Resolve a list of tool ids/names into tool objects; None means all."""
        if keys is None:
            return self.all()
        tools: list[Tool] = []
        seen: set[int] = set()
        for key in keys:
            t = self.get(key)
            if t is not None and id(t) not in seen:
                seen.add(id(t))
                tools.append(t)
        return tools

    def to_openai_schema(self, keys: list[str] | None = None) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self.resolve(keys)
        ]

    async def run(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, output="", error=f"unknown tool: {name}")
        return await tool.run(**kwargs)


def build_default_registry() -> ToolRegistry:
    from src.tools.builtin.calculator import CalculatorTool
    from src.tools.builtin.http import HttpTool

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(HttpTool())
    return registry
