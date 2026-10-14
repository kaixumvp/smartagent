import asyncio
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api_tool_executor import ApiToolCallError, call_api_tool
from ..database import get_db
from ..manifest import new_manifest
from ..models import ApiService, Tool
from ..schemas import ApiToolCreate, ToolOut, ToolTestRequest

router = APIRouter(prefix="/api-tools", tags=["api-tools"])
_PATH_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_FORBIDDEN_HEADERS = {
    "authorization",
    "connection",
    "content-length",
    "cookie",
    "host",
    "keep-alive",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _validate_tool_config(payload: ApiToolCreate) -> None:
    if not payload.path.startswith("/") or payload.path.startswith("//"):
        raise HTTPException(status_code=422, detail="Path must be a relative path starting with '/'")
    if any(char in payload.path for char in ("\r", "\n", "?")) or "://" in payload.path:
        raise HTTPException(status_code=422, detail="Path cannot contain a query string or absolute URL")
    if payload.input_schema.get("type", "object") != "object":
        raise HTTPException(status_code=422, detail="API Tool input_schema must describe a JSON object")
    properties = payload.input_schema.get("properties", {})
    if not isinstance(properties, dict):
        raise HTTPException(status_code=422, detail="API Tool input_schema properties must be an object")
    missing_parameters = set(_PATH_PARAMETER.findall(payload.path)) - set(properties)
    if missing_parameters:
        missing = ", ".join(sorted(missing_parameters))
        raise HTTPException(
            status_code=422,
            detail=f"Path parameters must be declared in input_schema properties: {missing}",
        )
    for name in payload.header_template:
        if not _HEADER_NAME.fullmatch(name) or name.lower() in _FORBIDDEN_HEADERS:
            raise HTTPException(status_code=422, detail=f"Header '{name}' cannot be set by a Tool")
    if not all(isinstance(name, str) for name in payload.query_template):
        raise HTTPException(status_code=422, detail="Query parameter names must be strings")


def _execution_config(payload: ApiToolCreate) -> dict[str, Any]:
    return {
        "kind": "http",
        "method": payload.method,
        "path": payload.path,
        "path_parameters": _PATH_PARAMETER.findall(payload.path),
        "query_template": payload.query_template,
        "header_template": payload.header_template,
        "body_template": payload.body_template,
    }


def _get_api_tool(db: Session, tool_id: uuid.UUID) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.source != "api" or tool.api_service_id is None:
        raise HTTPException(status_code=404, detail="API Tool not found")
    return tool


@router.post("", response_model=ToolOut, status_code=201)
def create_api_tool(payload: ApiToolCreate, db: Session = Depends(get_db)):
    _validate_tool_config(payload)
    service = db.get(ApiService, payload.api_service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="API service not found")
    manifest = new_manifest(
        display_name=payload.display_name,
        description=payload.description,
        version=payload.version,
        tags=payload.tags,
        keywords=payload.keywords,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        provider={"kind": "api_service", "api_service_id": str(service.id), "api_service_name": service.name},
    )
    manifest["execution"] = _execution_config(payload)
    tool = Tool(
        source="api",
        api_service_id=service.id,
        display_name=payload.display_name,
        description=payload.description,
        lifecycle_state=payload.lifecycle_state.value,
        enabled=payload.enabled,
        manifest=manifest,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@router.put("/{tool_id}", response_model=ToolOut)
def update_api_tool(tool_id: uuid.UUID, payload: ApiToolCreate, db: Session = Depends(get_db)):
    tool = _get_api_tool(db, tool_id)
    _validate_tool_config(payload)
    service = db.get(ApiService, payload.api_service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="API service not found")
    manifest = new_manifest(
        display_name=payload.display_name,
        description=payload.description,
        version=payload.version,
        tags=payload.tags,
        keywords=payload.keywords,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        provider={"kind": "api_service", "api_service_id": str(service.id), "api_service_name": service.name},
    )
    manifest["execution"] = _execution_config(payload)
    tool.api_service_id = service.id
    tool.display_name = payload.display_name
    tool.description = payload.description
    tool.lifecycle_state = payload.lifecycle_state.value
    tool.enabled = payload.enabled
    tool.manifest = manifest
    db.commit()
    db.refresh(tool)
    return tool


@router.post("/{tool_id}/test")
def test_api_tool(tool_id: uuid.UUID, payload: ToolTestRequest, db: Session = Depends(get_db)):
    tool = _get_api_tool(db, tool_id)
    service = db.get(ApiService, tool.api_service_id)
    if service is None:
        raise HTTPException(status_code=409, detail="API service not found")
    if not tool.enabled or tool.lifecycle_state != "active":
        raise HTTPException(status_code=409, detail="API Tool must be enabled and active to run")
    try:
        return asyncio.run(call_api_tool(service, tool, payload.arguments))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="API request timed out") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ApiToolCallError as exc:
        status = 504 if "timed out" in str(exc).lower() else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
