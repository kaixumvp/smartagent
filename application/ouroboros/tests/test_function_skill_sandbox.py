import os

import pytest

from src.plugins.base import InvokeContext, PluginManifest
from src.skills.function_skill import FunctionSkill


@pytest.mark.asyncio
async def test_function_skill_sandbox_blocks_import():
    """A payload attempting `__import__('os')` must not leak the host filesystem."""
    skill = FunctionSkill(
        PluginManifest(name="bad", kind="skill"),
        {"source": "def run(**kw):\n    return __import__('os').getcwd()"},
    )
    out = await skill.invoke(InvokeContext())
    assert "function skill error" in out
    assert os.getcwd() not in out  # the escaped payload never executed


@pytest.mark.asyncio
async def test_function_skill_timeout():
    skill = FunctionSkill(
        PluginManifest(name="slow", kind="skill"),
        {"source": "def run(**kw):\n    while True:\n        pass", "timeout": 0.2},
    )
    out = await skill.invoke(InvokeContext())
    assert "timed out" in out


@pytest.mark.asyncio
async def test_function_skill_inline_mode_still_works():
    skill = FunctionSkill(
        PluginManifest(name="add", kind="skill"),
        {"source": "def run(**kw):\n    return str(int(kw['a']) + int(kw['b']))", "sandbox": "inline"},
    )
    out = await skill.invoke(InvokeContext(), a=1, b=2)
    assert out == "3"
