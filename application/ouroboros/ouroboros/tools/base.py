from abc import ABC, abstractmethod
from typing import Any, Protocol

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str | dict
    error: str | None = None


class Tool(Protocol):
    """Tool abstraction protocol. From V0.2 it will be unified into the Plugin protocol, with Tool becoming a subtype of Plugin."""

    name: str
    description: str
    parameters: dict  # JSON Schema (for LLM function calling)
    permission: str  # read|write|admin

    async def run(self, **kwargs: Any) -> ToolResult: ...


class BaseTool(ABC):
    """Base class for builtin tools that satisfies the Tool protocol; subclasses only override run."""

    id: str = ""
    name: str = ""
    description: str = ""
    permission: str = "read"
    parameters: dict = {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult: ...
