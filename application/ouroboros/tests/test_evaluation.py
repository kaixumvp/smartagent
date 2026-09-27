import pytest

from src.evaluation import Case, GoldenSet, HeuristicJudge, run_evaluation


@pytest.mark.asyncio
async def test_heuristic_judge_contains_reference():
    j = HeuristicJudge()
    v = await j.judge(task="q", output="答案是 42", reference="42")
    assert v.passed is True
    v2 = await j.judge(task="q", output="不知道", reference="42")
    assert v2.passed is False


@pytest.mark.asyncio
async def test_heuristic_judge_without_reference():
    j = HeuristicJudge()
    assert (await j.judge(task="q", output="有内容")).passed is True
    assert (await j.judge(task="q", output="")).passed is False


@pytest.mark.asyncio
async def test_run_evaluation_single_case():
    from conftest import MockLLMGateway, build_default_plugins
    from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
    from src.core.resilience import RetryPolicy
    from src.llm.base import LLMResponse, Usage

    llm = MockLLMGateway([
        LLMResponse(content='[{"description": "answer"}]', usage=Usage()),
        LLMResponse(content="答案是 42", usage=Usage()),
    ])
    definition = AgentDefinition(model="m", system_prompt="s", plugins=build_default_plugins())
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0))
    rt = AgentRuntime()

    golden = GoldenSet(cases=[Case(id="c1", task="1+1?", reference="42")])
    results = await run_evaluation(rt, definition, deps, golden, HeuristicJudge(), RunContext(run_id="r1"))

    assert len(results) == 1
    assert results[0].case_id == "c1"
    assert results[0].verdict.passed is True
