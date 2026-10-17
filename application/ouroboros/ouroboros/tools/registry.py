import logging

from ouroboros.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Catalog of builtin tools indexed by name and id (a bare ``BaseTool`` lookup, pre-Plugin)."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        logger.debug("register tool: %s", tool.name)
        self._tools[tool.name] = tool
        tool_id = getattr(tool, "id", None)
        if tool_id:
            self._tools[tool_id] = tool

    def get(self, key: str) -> BaseTool | None:
        return self._tools.get(key)

    def all(self) -> list[BaseTool]:
        seen: set[int] = set()
        tools: list[BaseTool] = []
        for t in self._tools.values():
            if id(t) not in seen:
                seen.add(id(t))
                tools.append(t)
        return tools


def build_default_registry() -> ToolRegistry:
    from ouroboros.tools.builtin.calculator import CalculatorTool
    from ouroboros.tools.builtin.http import HttpTool

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(HttpTool())
    return registry
