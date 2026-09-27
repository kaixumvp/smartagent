import pytest

from src.llm.base import LLMResponse, Usage
from src.llm.replay import ReplayGateway, RecordingGateway, dump_recording, load_recording


class Scripted:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, messages, model=None, tools=None):
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_recording_gateway_records():
    inner = Scripted([LLMResponse(content="a"), LLMResponse(content="b")])
    rec = RecordingGateway(inner)
    assert (await rec.chat([])).content == "a"
    assert (await rec.chat([])).content == "b"
    assert [r.content for r in rec.recorded] == ["a", "b"]


@pytest.mark.asyncio
async def test_replay_gateway_replays_deterministically():
    rg = ReplayGateway([LLMResponse(content="a"), LLMResponse(content="b")])
    assert (await rg.chat([])).content == "a"
    assert (await rg.chat([])).content == "b"
    assert rg.calls == 2


@pytest.mark.asyncio
async def test_replay_exhausted_raises():
    rg = ReplayGateway([])
    with pytest.raises(RuntimeError):
        await rg.chat([])


def test_dump_and_load_recording(tmp_path):
    responses = [LLMResponse(content="a", usage=Usage(total_tokens=5))]
    path = tmp_path / "rec.json"
    dump_recording(responses, path)
    loaded = load_recording(path)
    assert loaded[0].content == "a"
    assert loaded[0].usage.total_tokens == 5
