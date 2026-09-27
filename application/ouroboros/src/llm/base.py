"""Deprecated: LLM contracts now live in ``ouroboros.ports`` (V0.3 consolidation).

Re-exported here for backward compatibility with V0.2 imports.
"""

from src.ports import LLMGateway, LLMResponse, ToolCall, Usage

__all__ = ["LLMGateway", "LLMResponse", "ToolCall", "Usage"]
