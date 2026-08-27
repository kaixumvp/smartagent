"""A/B traffic split (business service).

Assignment is **deterministic and sticky**: hashing `(experiment_id, subject_key)` to a point
in [0,1) and walking the weighted buckets means the same subject always lands in the same
variant. Random assignment would flip a user between variants request to request, which both
ruins their experience and makes the comparison meaningless.

Two rules keep it actually sticky:
- Weights are **frozen** on the experiment row. Changing them moves the bucket boundaries, so
  a subject whose hash point never moved would silently switch variants. Re-splitting traffic
  means creating a new experiment.
- The first assignment is persisted, so the split is auditable rather than merely recomputable.
"""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import AgentExperiment, ExperimentAssignment
from smartagent.util import new_id

logger = logging.getLogger(__name__)

_UINT64 = float(1 << 64)


def pick_variant(experiment_id: str, subject_key: str, variants: list[dict]) -> dict:
    """Weighted bucket for a subject. Pure and deterministic — safe to call anywhere."""
    if not variants:
        raise ValueError("experiment has no variants")
    digest = hashlib.sha256(f"{experiment_id}:{subject_key}".encode("utf-8")).digest()
    point = int.from_bytes(digest[:8], "big") / _UINT64

    total = sum(max(0.0, float(v.get("weight", 0))) for v in variants)
    if total <= 0:
        return variants[0]

    acc = 0.0
    for variant in variants:
        acc += max(0.0, float(variant.get("weight", 0))) / total
        if point < acc:
            return variant
    return variants[-1]  # guards the floating-point edge where acc lands just under 1.0


class ExperimentService:
    """Resolves which agent should serve a request, and remembers the decision."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find_running(self, tenant_id: str, entry_agent_id: str) -> AgentExperiment | None:
        """The running experiment whose entry point is this agent, if any."""
        return (
            await self._db.execute(
                select(AgentExperiment).where(
                    AgentExperiment.tenant_id == tenant_id,
                    AgentExperiment.entry_agent_id == entry_agent_id,
                    AgentExperiment.status == "running",
                )
            )
        ).scalars().first()

    async def assign(self, experiment: AgentExperiment, subject_key: str) -> ExperimentAssignment:
        """Read the subject's assignment, computing and persisting it on first sight."""
        existing = (
            await self._db.execute(
                select(ExperimentAssignment).where(
                    ExperimentAssignment.experiment_id == experiment.id,
                    ExperimentAssignment.subject_key == subject_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing

        variant = pick_variant(experiment.id, subject_key, experiment.variants or [])
        assignment = ExperimentAssignment(
            id=new_id("assign"),
            experiment_id=experiment.id,
            subject_key=subject_key,
            variant=str(variant.get("label") or variant.get("agent_id") or "?"),
            agent_id=str(variant.get("agent_id") or ""),
        )
        self._db.add(assignment)
        try:
            await self._db.commit()
        except IntegrityError:
            # Concurrent first request for the same subject won the unique index. Their row and
            # ours agree anyway (the bucket is a pure function), so just adopt the stored one.
            await self._db.rollback()
            return (
                await self._db.execute(
                    select(ExperimentAssignment).where(
                        ExperimentAssignment.experiment_id == experiment.id,
                        ExperimentAssignment.subject_key == subject_key,
                    )
                )
            ).scalars().one()
        return assignment


def subject_key_for(user_id: str | None, principal_user_id: str | None, run_id: str) -> str:
    """Pick the stickiest available identity for bucketing.

    Falls back to the run id, which makes assignment per-request rather than sticky — correct
    behaviour for an anonymous caller, but worth knowing when reading experiment results.
    """
    return user_id or principal_user_id or run_id


__all__ = ["ExperimentService", "pick_variant", "subject_key_for"]
