"""Deterministic record/replay of LLM responses (V1.1).

Record a run's responses with ``RecordingGateway``, then replay them offline with
``ReplayGateway`` so the *same* run reproduces the *same* result — the foundation for
offline evaluation and regression. ``dump_recording`` / ``load_recording`` persist a
recording to JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.ports import LLMResponse


class RecordingGateway:
    """Wraps a gateway and records every response, in call order."""

    def __init__(self, gateway) -> None:
        self._gateway = gateway
        self.recorded: list[LLMResponse] = []

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        resp = await self._gateway.chat(messages, model=model, tools=tools)
        self.recorded.append(resp)
        return resp


class ReplayGateway:
    """Plays back pre-recorded responses deterministically, ignoring any real LLM."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        if not self._responses:
            raise RuntimeError("replay exhausted: no recorded response for this call")
        self.calls += 1
        return self._responses.pop(0)


def dump_recording(responses: list[LLMResponse], path) -> None:
    Path(path).write_text(
        json.dumps([r.model_dump() for r in responses], ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def load_recording(path) -> list[LLMResponse]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [LLMResponse(**item) for item in data]


__all__ = ["RecordingGateway", "ReplayGateway", "dump_recording", "load_recording"]
