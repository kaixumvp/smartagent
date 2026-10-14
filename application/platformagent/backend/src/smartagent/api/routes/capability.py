from fastapi import APIRouter, Depends, HTTPException

from smartagent.adapters.capability_registry import (
    CapabilityRegistryClient,
    CapabilityRegistryError,
)
from smartagent.api.security import get_current_user, require_permission
from smartagent.config import get_settings
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/capability", tags=["capability-registry"])


def _client() -> CapabilityRegistryClient:
    settings = get_settings()
    return CapabilityRegistryClient(
        settings.capability_registry_url,
        settings.capability_integration_key,
    )


def _raise_upstream(exc: CapabilityRegistryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/providers")
async def list_capability_providers(
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:create")),
):
    del principal
    try:
        return await _client().list_providers()
    except CapabilityRegistryError as exc:
        raise _raise_upstream(exc)


@router.get("/tools")
async def list_capability_tools(
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:create")),
):
    del principal
    try:
        return await _client().list_tools()
    except CapabilityRegistryError as exc:
        raise _raise_upstream(exc)


@router.get("/providers/{provider_id}/tools")
async def list_capability_provider_tools(
    provider_id: str,
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("agent:create")),
):
    del principal
    try:
        return await _client().list_provider_tools(provider_id)
    except CapabilityRegistryError as exc:
        raise _raise_upstream(exc)
