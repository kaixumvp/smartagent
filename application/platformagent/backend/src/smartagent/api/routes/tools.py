import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.deps import get_tool_registry
from smartagent.api.schemas import ToolCreateRequest, ToolOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.db.models import Tool
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from src.tools.registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["tools"])


def _builtin_out(t) -> ToolOut:
    return ToolOut(
        id=getattr(t, "id", f"tool_{t.name}"),
        name=t.name,
        type="builtin",
        description=t.description,
        parameters=t.parameters,
        permission=getattr(t, "permission", "read"),
        requires_approval=False,
    )


def _db_out(tool: Tool) -> ToolOut:
    return ToolOut(
        id=tool.id,
        name=tool.name,
        type=tool.type,
        description=tool.description,
        parameters=tool.parameters,
        permission=tool.permission,
        requires_approval=tool.requires_approval,
    )


@router.get("", response_model=list[ToolOut])
async def list_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    # Builtin tools are available to every tenant; MCP/HTTP tools are tenant-scoped.
    builtin = [_builtin_out(t) for t in registry.all()]
    rows = (
        await db.execute(
            select(Tool).where(Tool.tenant_id == principal.tenant_id, Tool.type.in_(["mcp", "http"]))
        )
    ).scalars().all()
    return builtin + [_db_out(r) for r in rows]


@router.post("", response_model=ToolOut, status_code=201)
async def register_tool(
    body: ToolCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("tool:register")),
):
    tool = Tool(
        id=f"tool_{uuid.uuid4().hex}",
        tenant_id=principal.tenant_id,
        name=body.name,
        type=body.type,
        description=body.description,
        parameters=body.parameters,
        permission=body.permission,
        endpoint=body.endpoint,
        config=body.config,
        requires_approval=body.requires_approval,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return _db_out(tool)
