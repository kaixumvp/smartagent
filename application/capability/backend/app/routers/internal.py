import asyncio
import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..api_tool_executor import ApiToolCallError, call_api_tool
from ..mcp_auth import decrypt_auth_config
from ..mcp_client import call_remote_tool
from ..models import ApiService, Provider, Tool
from ..schemas import ToolTestRequest

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def require_integration_key(
    integration_key: str | None = Header(default=None, alias="X-Capability-Integration-Key"),
) -> None:
    expected = settings.capability_integration_key
    if not expected:
        raise HTTPException(status_code=503, detail="Capability integration key is not configured")
    if integration_key is None or not hmac.compare_digest(integration_key, expected):
        raise HTTPException(status_code=401, detail="Invalid integration key")


@router.get("/providers", dependencies=[Depends(require_integration_key)])
def list_integration_providers(db: Session = Depends(get_db)):
    providers = db.query(Provider).order_by(Provider.name).all()
    return [
        {
            "id": str(provider.id),
            "name": provider.name,
            "status": provider.status,
            "auth_type": provider.auth_type,
            "has_authentication": provider.has_authentication,
        }
        for provider in providers
    ]


@router.get("/providers/{provider_id}/tools", dependencies=[Depends(require_integration_key)])
def list_integration_tools(provider_id: uuid.UUID, db: Session = Depends(get_db)):
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="MCP Provider not found")

    tools = (
        db.query(Tool)
        .filter(
            Tool.provider_id == provider.id,
            Tool.source == "mcp",
            Tool.enabled.is_(True),
            Tool.lifecycle_state != "remote_missing",
        )
        .order_by(Tool.display_name)
        .all()
    )
    return [
        {
            "id": str(tool.id),
            "name": tool.remote_tool_name,
            "display_name": tool.display_name,
            "description": tool.description,
            "input_schema": (tool.manifest or {}).get("contract", {}).get("input_schema") or {},
        }
        for tool in tools
    ]


@router.get("/tools", dependencies=[Depends(require_integration_key)])
def list_all_integration_tools(db: Session = Depends(get_db)):
    tools = (
        db.query(Tool, Provider.name, ApiService.name)
        .outerjoin(Provider, Tool.provider_id == Provider.id)
        .outerjoin(ApiService, Tool.api_service_id == ApiService.id)
        .filter(
            Tool.source.in_(["mcp", "api"]),
            Tool.enabled.is_(True),
            Tool.lifecycle_state == "active",
            or_(
                and_(Tool.source == "mcp", Provider.id.is_not(None)),
                and_(
                    Tool.source == "api",
                    ApiService.id.is_not(None),
                    ApiService.enabled.is_(True),
                ),
            ),
        )
        .order_by(Tool.display_name)
        .all()
    )
    available = []
    for tool, provider_name, service_name in tools:
        if tool.source == "mcp":
            if not provider_name or not tool.remote_tool_name:
                continue
            name = tool.remote_tool_name
            owner = provider_name
        else:
            if not service_name:
                continue
            execution = (tool.manifest or {}).get("execution") or {}
            name = (tool.manifest or {}).get("identity", {}).get("name") or tool.display_name
            owner = service_name
            permission = "read" if execution.get("method") == "GET" else "write"
        if tool.source == "mcp":
            permission = "read"
        available.append(
            {
                "id": str(tool.id),
                "source": tool.source,
                "provider_id": str(tool.provider_id) if tool.provider_id else None,
                "service_id": str(tool.api_service_id) if tool.api_service_id else None,
                "service_name": owner,
                "name": name,
                "display_name": tool.display_name,
                "description": tool.description,
                "input_schema": (tool.manifest or {}).get("contract", {}).get("input_schema") or {},
                "permission": permission,
            }
        )
    return available


@router.post("/tools/{tool_id}/call", dependencies=[Depends(require_integration_key)])
def invoke_integration_tool(
    tool_id: uuid.UUID,
    payload: ToolTestRequest,
    db: Session = Depends(get_db),
):
    tool = db.get(Tool, tool_id)
    if (
        tool is None
        or not tool.enabled
        or (tool.source == "api" and tool.lifecycle_state != "active")
        or (tool.source == "mcp" and tool.lifecycle_state == "remote_missing")
    ):
        raise HTTPException(status_code=404, detail="Available Capability Tool not found")

    if tool.source == "api":
        service = db.get(ApiService, tool.api_service_id) if tool.api_service_id else None
        if service is None:
            raise HTTPException(status_code=404, detail="API service not found")
        try:
            return asyncio.run(call_api_tool(service, tool, payload.arguments))
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="API request timed out") from exc
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ApiToolCallError as exc:
            status = 504 if "timed out" in str(exc).lower() else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    if tool.source != "mcp" or tool.provider_id is None or not tool.remote_tool_name:
        raise HTTPException(status_code=404, detail="Available Capability Tool not found")
    provider = db.get(Provider, tool.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="MCP Provider not found")

    try:
        auth_config = decrypt_auth_config(provider.auth_config_encrypted)
        return asyncio.run(
            call_remote_tool(
                provider.endpoint,
                tool.remote_tool_name,
                payload.arguments,
                provider.auth_type,
                auth_config,
            )
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="MCP Tool call timed out") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - expose remote failures without hiding the cause
        from ..mcp_client import describe_mcp_error

        raise HTTPException(status_code=502, detail=describe_mcp_error(exc)) from exc
