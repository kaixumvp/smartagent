"""Asynchronous evaluation jobs (business service).

A golden set can hold hundreds of cases and each one is a full agent run, so evaluation runs
in the background and the caller polls. That shape forces three things to be right:

1. **The task must be strongly referenced.** A bare `asyncio.create_task(...)` whose result is
   discarded can be garbage-collected mid-flight, so handles are held in `_TASKS` until done.
2. **Every case needs its own session.** `AsyncSession` is not safe for concurrent use — the
   same reason `DbSubagentRunner` opens its own (`adapters/subagent_runner.py`). Concurrency is
   bounded by `settings.eval_concurrency`, and each case commits independently so a crash keeps
   the cases that already finished.
3. **Dependencies must be rebuilt, not borrowed.** The request's session is closed once the
   response is sent. `Principal` is carried over (there is no JWT in a background task), but
   `PermissionContext` is re-derived against a fresh session, since evaluation cases invoke
   real tools and a stale authorization snapshot would misjudge them.

**Why not `ouroboros.evaluation.run_evaluation`** (`evaluation/golden.py:31`): it calls
`runtime.run` directly with one shared `deps` for every case. That `deps` carries a single
`RunRecorder` and `DbCheckpointer`, both bound to one `run_id`, so every case's steps and
checkpoints would pile onto one row — and it creates no `runs` rows at all. The framework's
`Case`/`GoldenSet`/`JudgeVerdict`/`HeuristicJudge` are reused; only the loop is ours.
"""

import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.llm_judge import LlmJudge
from smartagent.db.models import Agent, Evaluation, EvaluationResult, GoldenCase, Run
from smartagent.db.session import SessionLocal
from smartagent.iam.permission_manager import PermissionManager
from smartagent.services.run_service import RunService
from smartagent.util import new_id, utcnow
from ouroboros.evaluation import HeuristicJudge

logger = logging.getLogger(__name__)

# Strong references to in-flight jobs. Without this CPython may collect a task whose only
# reference was the discarded return value of create_task().
_TASKS: set[asyncio.Task] = set()


def launch(job: "EvaluationJob") -> asyncio.Task:
    """Fire an evaluation in the background and keep it alive until it finishes."""
    task = asyncio.create_task(job.execute())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


class EvaluationJob:
    """One evaluation, executed off the request path with its own database sessions."""

    def __init__(
        self,
        *,
        evaluation_id: str,
        principal,
        settings,
        llm,
        judge_gateway,
        memory,
        tool_registry,
        session_factory=SessionLocal,
    ) -> None:
        self._evaluation_id = evaluation_id
        self._principal = principal
        self._settings = settings
        self._llm = llm
        self._judge_gateway = judge_gateway
        self._memory = memory
        self._tool_registry = tool_registry
        self._session_factory = session_factory

    # ------------------------------------------------------------------ lifecycle
    async def execute(self) -> None:
        try:
            async with self._session_factory() as db:
                evaluation, agent, cases, permission_context = await self._prepare(db)
                if evaluation is None:
                    return

            results = await self._run_cases(evaluation, agent, cases, permission_context)

            async with self._session_factory() as db:
                await self._summarize(db, results)
        except Exception as exc:  # noqa: BLE001 — a job must never die silently
            logger.exception("evaluation failed: id=%s", self._evaluation_id)
            await self._mark_failed(str(exc))

    async def _prepare(self, db: AsyncSession):
        evaluation = await db.get(Evaluation, self._evaluation_id)
        if evaluation is None:
            logger.warning("evaluation %s vanished before it started", self._evaluation_id)
            return None, None, [], None
        agent = await db.get(Agent, evaluation.agent_id)
        if agent is None:
            raise RuntimeError(f"agent {evaluation.agent_id} not found")

        cases = (
            await db.execute(
                select(GoldenCase)
                .where(GoldenCase.golden_set_id == evaluation.golden_set_id)
                .order_by(GoldenCase.created_at, GoldenCase.id)
            )
        ).scalars().all()

        # Re-derive authorization against this session; the request's snapshot is gone.
        permission_context = await PermissionManager().build_context(db, self._principal)

        evaluation.status = "running"
        evaluation.started_at = utcnow()
        evaluation.total = len(cases)
        await db.commit()

        # Detach: the session closes when `_prepare`'s caller exits its `async with`.
        detached_cases = [
            {"id": c.id, "task": c.task, "reference": c.reference} for c in cases
        ]
        return evaluation, agent, detached_cases, permission_context

    async def _run_cases(self, evaluation, agent, cases, permission_context) -> list[dict]:
        semaphore = asyncio.Semaphore(max(1, self._settings.eval_concurrency))
        agent_id = agent.id
        tenant_id = evaluation.tenant_id
        judge = self._build_judge(evaluation)

        async def one(case: dict) -> dict:
            async with semaphore:
                return await self._run_case(case, agent_id, tenant_id, permission_context, judge)

        return list(await asyncio.gather(*(one(case) for case in cases)))

    def _build_judge(self, evaluation):
        if evaluation.judge_type == "heuristic":
            return HeuristicJudge()
        return LlmJudge(self._judge_gateway, evaluation.judge_model or self._settings.llm_model)

    # ------------------------------------------------------------------ one case
    async def _run_case(self, case: dict, agent_id, tenant_id, permission_context, judge) -> dict:
        started = time.perf_counter()
        async with self._session_factory() as db:
            record = EvaluationResult(
                id=new_id("evalres"),
                evaluation_id=self._evaluation_id,
                case_id=case["id"],
            )
            try:
                agent = await db.get(Agent, agent_id)
                if agent is None:
                    raise RuntimeError(f"agent {agent_id} not found")

                service = RunService(
                    db=db,
                    llm=self._llm,
                    memory=self._memory,
                    settings=self._settings,
                    principal=self._principal,
                    permission_context=permission_context,
                    permission_manager=PermissionManager(),
                    tool_registry=self._tool_registry,
                    memory_write_back=False,  # synthetic workload — keep it out of long-term memory
                )
                registry = await service.load_registry(db, agent)

                run = Run(
                    id=new_id("run"),
                    agent_id=agent.id,
                    tenant_id=tenant_id,
                    user_id=None,
                    input=case["task"],
                    status="running",
                    evaluation_id=self._evaluation_id,
                    created_at=utcnow(),
                    started_at=utcnow(),
                )
                db.add(run)
                await db.commit()
                record.run_id = run.id

                result = await service.start(
                    agent,
                    run,
                    task=case["task"],
                    user_id=None,
                    # A per-case session id keeps evaluation history out of any real session.
                    registry=registry,
                )
                await service.finalize(agent, run, result, user_id=None)

                if result.status == "awaiting_human":
                    # Nobody can approve inside an offline evaluation, so this is a failed case
                    # rather than a pause — say why, instead of scoring an empty answer.
                    record.output = ""
                    record.score = 0.0
                    record.passed = False
                    record.reason = "run paused for human approval; not scoreable offline"
                else:
                    output = result.result or ""
                    verdict = await judge.judge(
                        task=case["task"], output=output, reference=case.get("reference")
                    )
                    record.output = output
                    record.score = verdict.score
                    record.passed = verdict.passed
                    record.reason = verdict.reason

                record.token_usage = result.token_usage
                record.cost = float(run.cost or 0)
            except Exception as exc:  # noqa: BLE001 — one bad case must not sink the job
                logger.exception("evaluation case failed: eval=%s case=%s", self._evaluation_id, case["id"])
                await db.rollback()
                record.passed = False
                record.score = 0.0
                record.error = str(exc)
                record.reason = "case raised an exception"

            record.latency_ms = int((time.perf_counter() - started) * 1000)
            db.add(record)
            await db.commit()
            return {"passed": record.passed, "score": float(record.score or 0), "cost": float(record.cost or 0)}

    # ------------------------------------------------------------------ summary
    async def _summarize(self, db: AsyncSession, results: list[dict]) -> None:
        evaluation = await db.get(Evaluation, self._evaluation_id)
        if evaluation is None:
            return
        passed = sum(1 for r in results if r["passed"])
        evaluation.total = len(results)
        evaluation.passed = passed
        evaluation.failed = len(results) - passed
        evaluation.avg_score = round(sum(r["score"] for r in results) / len(results), 4) if results else 0.0
        evaluation.cost = round(sum(r["cost"] for r in results), 6)
        evaluation.status = "completed"
        evaluation.finished_at = utcnow()
        await db.commit()

    async def _mark_failed(self, error: str) -> None:
        try:
            async with self._session_factory() as db:
                evaluation = await db.get(Evaluation, self._evaluation_id)
                if evaluation is None:
                    return
                evaluation.status = "failed"
                evaluation.error = error[:1000]
                evaluation.finished_at = utcnow()
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not record evaluation failure: id=%s", self._evaluation_id)


async def sweep_interrupted(session_factory=SessionLocal) -> int:
    """Fail evaluations (and their runs) left mid-flight by a process restart.

    Scoped to `runs.evaluation_id IS NOT NULL` on purpose: blanket-failing every `awaiting_human`
    run would kill legitimate interactive HITL runs that were correctly waiting for a human.
    """
    async with session_factory() as db:
        stale = (
            await db.execute(
                select(Evaluation).where(Evaluation.status.in_(("queued", "running")))
            )
        ).scalars().all()
        if not stale:
            return 0

        ids = [e.id for e in stale]
        for evaluation in stale:
            evaluation.status = "failed"
            evaluation.error = "interrupted by a process restart"
            evaluation.finished_at = utcnow()

        orphan_runs = (
            await db.execute(
                select(Run).where(
                    Run.evaluation_id.in_(ids),
                    Run.status.in_(("running", "awaiting_human")),
                )
            )
        ).scalars().all()
        for run in orphan_runs:
            run.status = "failed"
            run.error = "interrupted by a process restart"
            run.finished_at = utcnow()

        await db.commit()
        logger.warning("swept %d interrupted evaluations (%d runs)", len(stale), len(orphan_runs))
        return len(stale)


__all__ = ["EvaluationJob", "launch", "sweep_interrupted"]
