"""Evaluation closed loop: judging, and the async job that scores a golden set (V1.1)."""

import pytest

from conftest import (
    FakeMemoryManager,
    FakeSession,
    MockLLMGateway,
    admin_principal,
    session_factory_for,
)
from smartagent.adapters.llm_judge import LlmJudge
from smartagent.config import Settings
from smartagent.db.models import Agent, Evaluation, EvaluationResult, GoldenCase, Run
from smartagent.services.evaluation_service import EvaluationJob, sweep_interrupted
from src.llm.base import LLMResponse, Usage
from src.tools.registry import build_default_registry


class ScriptedGateway:
    """Returns preset contents in order; unlike MockLLMGateway it never runs dry."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        self.calls += 1
        content = self._contents.pop(0) if self._contents else self._contents_default()
        return LLMResponse(content=content, usage=Usage())

    @staticmethod
    def _contents_default() -> str:
        return '{"score": 1.0, "passed": true, "reason": "ok"}'


# --------------------------------------------------------------------------- judge
@pytest.mark.asyncio
async def test_llm_judge_parses_a_clean_verdict():
    judge = LlmJudge(ScriptedGateway(['{"score": 0.8, "passed": true, "reason": "close enough"}']), "m")

    verdict = await judge.judge(task="q", output="a", reference="a")

    assert (verdict.score, verdict.passed, verdict.reason) == (0.8, True, "close enough")


@pytest.mark.asyncio
async def test_llm_judge_tolerates_code_fences_and_prose():
    content = 'Sure!\n```json\n{"score": 0.4, "passed": false, "reason": "missing detail"}\n```'
    judge = LlmJudge(ScriptedGateway([content]), "m")

    verdict = await judge.judge(task="q", output="a")

    assert verdict.passed is False
    assert verdict.score == 0.4


@pytest.mark.asyncio
async def test_llm_judge_degrades_on_unparseable_output():
    """An unparseable verdict must not abort the evaluation, and must be visibly degraded
    rather than passed off as a real score."""
    judge = LlmJudge(ScriptedGateway(["I cannot score this."]), "m")

    verdict = await judge.judge(task="q", output="some answer")

    assert verdict.passed is True  # presence check
    assert "[degraded]" in verdict.reason


@pytest.mark.asyncio
async def test_llm_judge_degrades_when_the_gateway_raises():
    class Broken:
        async def chat(self, *a, **kw):
            raise RuntimeError("judge offline")

    verdict = await LlmJudge(Broken(), "m").judge(task="q", output="")

    assert verdict.passed is False
    assert "[degraded]" in verdict.reason


@pytest.mark.asyncio
async def test_llm_judge_clamps_and_infers_missing_fields():
    judge = LlmJudge(ScriptedGateway(['{"score": 5}']), "m")

    verdict = await judge.judge(task="q", output="a")

    assert verdict.score == 1.0  # clamped into 0..1
    assert verdict.passed is True  # inferred from the score


# --------------------------------------------------------------------------- async job
def _agent() -> Agent:
    return Agent(
        id="agent_test", tenant_id="default", name="t", version="1",
        config={"model": "test", "tools": ["tool_calculator"]}, status="active", is_latest=True,
    )


def _evaluation(judge_type: str = "heuristic") -> Evaluation:
    return Evaluation(
        id="eval_1", tenant_id="default", golden_set_id="gset_1", agent_id="agent_test",
        status="queued", judge_type=judge_type, judge_model="judge-model",
        total=0, passed=0, failed=0, avg_score=0, cost=0,
    )


def _cases(n: int) -> list[GoldenCase]:
    return [
        GoldenCase(id=f"gcase_{i}", golden_set_id="gset_1", task=f"question {i}", reference="42")
        for i in range(n)
    ]


def _agent_llm(answers: list[str]) -> MockLLMGateway:
    """Two LLM turns per case: a plan, then a final answer (no tool call)."""
    responses = []
    for answer in answers:
        responses.append(LLMResponse(content='[{"description": "answer"}]', usage=Usage()))
        responses.append(LLMResponse(content=answer, usage=Usage()))
    return MockLLMGateway(responses)


def _job(db: FakeSession, llm, judge_gateway=None) -> EvaluationJob:
    return EvaluationJob(
        evaluation_id="eval_1",
        principal=admin_principal(),
        settings=Settings(eval_concurrency=2),
        llm=llm,
        judge_gateway=judge_gateway or ScriptedGateway([]),
        memory=FakeMemoryManager(),
        tool_registry=build_default_registry(),
        session_factory=session_factory_for(db),
    )


@pytest.mark.asyncio
async def test_evaluation_scores_every_case_with_its_own_run():
    evaluation = _evaluation()
    db = FakeSession(evaluation, _agent(), *_cases(3))
    # Case 2's answer misses the reference, so it must fail.
    llm = _agent_llm(["the answer is 42", "the answer is 42", "no idea"])

    await _job(db, llm).execute()

    assert evaluation.status == "completed"
    assert (evaluation.total, evaluation.passed, evaluation.failed) == (3, 2, 1)
    assert evaluation.avg_score == pytest.approx(2 / 3, abs=1e-4)

    results = db.rows(EvaluationResult)
    assert len(results) == 3
    # Every case gets its own run row — the whole reason the framework's run_evaluation,
    # which shares one deps/run_id across cases, could not be reused here.
    run_ids = {r.run_id for r in results}
    assert len(run_ids) == 3 and None not in run_ids
    assert len(db.rows(Run)) == 3
    assert all(r.evaluation_id == "eval_1" for r in db.rows(Run))


@pytest.mark.asyncio
async def test_evaluation_does_not_write_back_to_long_term_memory():
    """Evaluation is synthetic traffic; folding its answers into memory would poison recall
    for real users."""
    evaluation = _evaluation()
    db = FakeSession(evaluation, _agent(), *_cases(1))
    memory = FakeMemoryManager()

    job = _job(db, _agent_llm(["the answer is 42"]))
    job._memory = memory
    await job.execute()

    # The user turn is still written (the runtime needs the history), but no assistant turn
    # is folded back in.
    roles = [m["role"] for msgs in memory.history.values() for m in msgs]
    assert "assistant" not in roles


@pytest.mark.asyncio
async def test_one_failing_case_does_not_sink_the_job():
    class BreaksOnOneCase:
        """Fails persistently for a single case. A transient failure would not do: the
        framework retries (`ouroboros/core/resilience.py`), so an intermittent error simply
        succeeds on the next attempt."""

        async def chat(self, messages, model=None, tools=None):
            if any("question 1" in str(m.get("content", "")) for m in messages):
                raise RuntimeError("model exploded")
            return LLMResponse(content="the answer is 42", usage=Usage())

    evaluation = _evaluation()
    db = FakeSession(evaluation, _agent(), *_cases(2))

    await _job(db, BreaksOnOneCase()).execute()

    # The job still finished and recorded every case; only the broken one is marked failed.
    assert evaluation.status == "completed"
    assert len(db.rows(EvaluationResult)) == 2
    assert (evaluation.passed, evaluation.failed) == (1, 1)
    broken = next(r for r in db.rows(EvaluationResult) if r.case_id == "gcase_1")
    assert broken.passed is False


@pytest.mark.asyncio
async def test_missing_agent_marks_the_evaluation_failed():
    evaluation = _evaluation()
    db = FakeSession(evaluation, *_cases(1))  # no agent row

    await _job(db, _agent_llm([])).execute()

    assert evaluation.status == "failed"
    assert "agent_test" in (evaluation.error or "")


@pytest.mark.asyncio
async def test_sweep_fails_interrupted_evaluations_and_their_runs():
    evaluation = _evaluation()
    evaluation.status = "running"
    eval_run = Run(
        id="run_eval", agent_id="agent_test", tenant_id="default", input="x",
        status="running", evaluation_id="eval_1",
    )
    # An interactive run legitimately waiting for a human — must survive the sweep.
    hitl_run = Run(
        id="run_hitl", agent_id="agent_test", tenant_id="default", input="y",
        status="awaiting_human", evaluation_id=None,
    )
    db = FakeSession(evaluation, eval_run, hitl_run)

    swept = await sweep_interrupted(session_factory=session_factory_for(db))

    assert swept == 1
    assert evaluation.status == "failed"
    assert eval_run.status == "failed"
    assert hitl_run.status == "awaiting_human"  # untouched
