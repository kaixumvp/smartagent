"""Ouroboros — a business-agnostic agent runtime."""

import logging

__version__ = "1.1.0"

from src.core.runtime import (  # noqa: E402
    AgentDefinition,
    AgentRuntime,
    RunContext,
    RunResult,
    RuntimeConfig,
    RuntimeDeps,
    Step,
)

__all__ = [
    "__version__",
    "AgentRuntime",
    "AgentDefinition",
    "RunContext",
    "RunResult",
    "RuntimeConfig",
    "RuntimeDeps",
    "Step",
]

# Library best practice: attach a NullHandler so an unconfigured host doesn't emit
# "No handlers could be found" warnings from our loggers.
logging.getLogger("src").addHandler(logging.NullHandler())
