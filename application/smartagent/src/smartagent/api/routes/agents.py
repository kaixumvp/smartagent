import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import AgentCreateRequest, AgentOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.db.models import Agent
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        version=agent.version,
        status=agent.status,
        config=agent.config,
        is_latest=agent.is_latest,
    )


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:create")),
):
    # Same versioning contract as skills (see routes/skills.py): posting a name that already
    # exists publishes a new version of that logical agent, and the new one becomes latest.
    # Version grouping is what A/B experiments compare across.
    siblings = (
        await db.execute(
            select(Agent).where(Agent.tenant_id == principal.tenant_id, Agent.name == body.name)
        )
    ).scalars().all()
    if any(s.version == body.version for s in siblings):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_STATE",
                "message": f"agent '{body.name}' version '{body.version}' already exists",
            },
        )
    for sibling in siblings:
        sibling.is_latest = False

    agent = Agent(
        id=f"agent_{uuid.uuid4().hex}",
        tenant_id=principal.tenant_id,
        name=body.name,
        version=body.version,
        config=body.config,
        status="active",
        is_latest=True,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    agents = (
        await db.execute(select(Agent).where(Agent.tenant_id == principal.tenant_id))
    ).scalars().all()
    return [_to_out(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {agent_id} not found"},
        )
    return _to_out(agent)
