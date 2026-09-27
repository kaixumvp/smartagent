"""Offline evaluation over a Golden Set (V1.1).

``run_evaluation`` runs the agent on each case and scores the output with a ``Judge`` port.
A dependency-free ``HeuristicJudge`` (reference-contains) is provided for smoke evals;
production hosts inject an LLM-as-judge behind the same protocol.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.ports import JudgeVerdict


class Case(BaseModel):
    id: str
    task: str
    reference: str | None = None  # expected/ideal answer the judge can compare against


class GoldenSet(BaseModel):
    cases: list[Case] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    case_id: str
    output: str
    verdict: JudgeVerdict


async def run_evaluation(runtime, definition, deps, golden: GoldenSet, judge, context) -> list[EvaluationResult]:
    """Run each golden case through the runtime and judge the output."""
    results: list[EvaluationResult] = []
    for case in golden.cases:
        run = await runtime.run(definition, case.task, context, deps)
        verdict = await judge.judge(task=case.task, output=run.result or "", reference=case.reference)
        results.append(EvaluationResult(case_id=case.id, output=run.result or "", verdict=verdict))
    return results


class HeuristicJudge:
    """Reference-match judge (contains), for tests and smoke evals without an LLM."""

    async def judge(self, *, task: str, output: str, reference: str | None = None) -> JudgeVerdict:
        if reference is None:
            passed = bool(output)
            return JudgeVerdict(score=1.0 if passed else 0.0, passed=passed,
                                reason="output present" if passed else "empty output")
        passed = reference in output
        return JudgeVerdict(
            score=1.0 if passed else 0.0,
            passed=passed,
            reason="reference matched" if passed else "reference not found in output",
        )


__all__ = ["Case", "GoldenSet", "EvaluationResult", "run_evaluation", "HeuristicJudge"]
