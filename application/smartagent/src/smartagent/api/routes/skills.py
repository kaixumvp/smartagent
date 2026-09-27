import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import SkillCreateRequest, SkillOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.db.models import Skill
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/skills", tags=["skills"])


def _to_out(skill: Skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        tenant_id=skill.tenant_id,
        name=skill.name,
        version=skill.version,
        type=skill.type,
        description=skill.description,
        is_latest=skill.is_latest,
        status=skill.status,
    )


@router.post("", response_model=SkillOut, status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("skill:register")),
):
    manifest = {
        "description": body.description,
        "parameters": body.parameters,
        "permission": body.permission,
        "requires_approval": body.requires_approval,
        "tags": body.tags,
    }
    # A new version becomes latest; clear the flag on any existing versions of the same name.
    previous = (
        await db.execute(
            select(Skill).where(Skill.tenant_id == principal.tenant_id, Skill.name == body.name)
        )
    ).scalars().all()
    for row in previous:
        row.is_latest = False

    skill = Skill(
        id=f"skill_{uuid.uuid4().hex}",
        tenant_id=principal.tenant_id,
        name=body.name,
        version=body.version,
        type=body.type,
        description=body.description,
        manifest=manifest,
        body=body.body,
        is_latest=True,
        status="active",
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_out(skill)


@router.get("", response_model=list[SkillOut])
async def list_skills(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    rows = (
        await db.execute(select(Skill).where(Skill.tenant_id == principal.tenant_id))
    ).scalars().all()
    return [_to_out(s) for s in rows]


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": f"skill {skill_id} not found"})
    return _to_out(skill)
