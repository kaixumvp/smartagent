import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.schemas import AgentCreateRequest, AgentOut, AgentUpdateRequest
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
            select(Agent).where(
                Agent.tenant_id == principal.tenant_id,
                Agent.name == body.name,
                Agent.status == "active",
            )
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
        await db.execute(
            select(Agent).where(Agent.tenant_id == principal.tenant_id, Agent.status == "active")
        )
    ).scalars().all()
    return [_to_out(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id or agent.status != "active":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {agent_id} not found"},
        )
    return _to_out(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:edit")),
):
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id or agent.status != "active":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {agent_id} not found"},
        )
    agent.config = body.config
    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:delete")),
):
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id or agent.status != "active":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {agent_id} not found"},
        )

    siblings = (
        await db.execute(
            select(Agent)
            .where(
                Agent.tenant_id == principal.tenant_id,
                Agent.name == agent.name,
                Agent.status == "active",
                Agent.id != agent.id,
            )
            .order_by(Agent.created_at.desc())
        )
    ).scalars().all()
    promote = siblings[0] if agent.is_latest and siblings else None

    agent.status = "deleted"
    agent.is_latest = False
    await db.flush()
    if promote is not None:
        promote.is_latest = True
    await db.commit()
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="agent.delete",
        result="success",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent.id,
        trace_id=getattr(request.state, "trace_id", None),
        detail={"name": agent.name, "version": agent.version},
    )
    return Response(status_code=204)
