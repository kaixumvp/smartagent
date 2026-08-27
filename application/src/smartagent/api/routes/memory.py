from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.deps import get_memory_manager
from smartagent.api.schemas import MemoryEntryOut, MemoryRecallRequest
from smartagent.api.security import get_current_user
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from ouroboros.memory.manager import MemoryManager

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/recall", response_model=list[MemoryEntryOut])
async def recall(
    body: MemoryRecallRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    memory: MemoryManager = Depends(get_memory_manager),
):
    """Recall long-term memories for the current tenant/user (debug/evaluation helper)."""
    entries = await memory.recall(db, principal.tenant_id, body.user_id, body.query, top_k=body.top_k)
    return [
        MemoryEntryOut(
            id=e.id,
            content=e.content,
            similarity=e.similarity,
            importance=e.importance,
            confidence=e.confidence,
        )
        for e in entries
    ]
