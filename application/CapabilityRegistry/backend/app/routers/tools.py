import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..manifest import new_manifest, slugify
from ..models import Tool
from ..schemas import ToolCreate, ToolOut, ToolUpdate

router = APIRouter(prefix="/tools", tags=["tools"])


def _get_tool_or_404(db: Session, tool_id: uuid.UUID) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.post("", response_model=ToolOut, status_code=201)
def create_tool(payload: ToolCreate, db: Session = Depends(get_db)):
    tool = Tool(
        source="local",
        display_name=payload.display_name,
        description=payload.description,
        lifecycle_state=payload.lifecycle_state.value,
        enabled=payload.enabled,
    )
    tool.manifest = new_manifest(
        display_name=payload.display_name,
        description=payload.description,
        version=payload.version,
        tags=payload.tags,
        keywords=payload.keywords,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@router.get("", response_model=list[ToolOut])
def list_tools(
    q: str | None = Query(default=None),
    provider_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Tool)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Tool.display_name.ilike(like), Tool.description.ilike(like)))
    if provider_id is not None:
        query = query.filter(Tool.provider_id == provider_id)
    return query.order_by(Tool.created_at.desc()).all()


@router.get("/{tool_id}", response_model=ToolOut)
def get_tool(tool_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_tool_or_404(db, tool_id)


@router.put("/{tool_id}", response_model=ToolOut)
def update_tool(tool_id: uuid.UUID, payload: ToolUpdate, db: Session = Depends(get_db)):
    tool = _get_tool_or_404(db, tool_id)
    data = payload.model_dump(exclude_unset=True)

    # 顶层列（用于列表/搜索/排序）
    if "display_name" in data:
        tool.display_name = data["display_name"]
    if "description" in data:
        tool.description = data["description"]
    if "lifecycle_state" in data:
        v = data["lifecycle_state"]
        tool.lifecycle_state = v.value if hasattr(v, "value") else v
    if "enabled" in data:
        tool.enabled = data["enabled"]

    # manifest 只做局部合并
    m = dict(tool.manifest or {})
    identity = dict(m.get("identity") or {})
    metadata = dict(m.get("metadata") or {})
    contract = dict(m.get("contract") or {})

    if "display_name" in data:
        identity["name"] = slugify(data["display_name"])
        identity["display_name"] = data["display_name"]
    if "version" in data:
        identity["version"] = data["version"]
    if "description" in data:
        metadata["description"] = data["description"]
    if "tags" in data:
        metadata["tags"] = data["tags"]
    if "keywords" in data:
        metadata["keywords"] = data["keywords"]
    if "input_schema" in data:
        contract["input_schema"] = data["input_schema"]
    if "output_schema" in data:
        contract["output_schema"] = data["output_schema"]

    m["identity"] = identity
    m["metadata"] = metadata
    m["contract"] = contract
    tool.manifest = m

    db.commit()
    db.refresh(tool)
    return tool


@router.delete("/{tool_id}", status_code=204)
def delete_tool(tool_id: uuid.UUID, db: Session = Depends(get_db)):
    tool = _get_tool_or_404(db, tool_id)
    db.delete(tool)
    db.commit()
    return None
