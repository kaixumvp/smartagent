from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str | dict
    error: str | None = None


class BaseTool(ABC):
    """Base class for run-based tools; subclasses only override ``run``."""

    id: str = ""
    name: str = ""
    description: str = ""
    permission: str = "read"
    parameters: dict = {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult: ...


# Backward-compatible alias: ``Tool`` was a structural Protocol before being folded into
# ``BaseTool``. Hosts importing ``ouroboros.tools.Tool`` still resolve it.
Tool = BaseTool
