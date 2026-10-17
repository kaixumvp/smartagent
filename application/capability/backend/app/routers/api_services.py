import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api_tool_executor import validate_service_url
from ..database import get_db
from ..mcp_auth import (
    decrypt_auth_config,
    encrypt_auth_config,
    reject_secret_query_params,
    validate_auth_config,
)
from ..models import ApiService, Tool
from ..schemas import ApiServiceCreate, ApiServiceOut, ApiServiceUpdate

router = APIRouter(prefix="/api-services", tags=["api-services"])


def _get_service_or_404(db: Session, service_id: uuid.UUID) -> ApiService:
    service = db.get(ApiService, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="API service not found")
    return service


def _validate_base_url(base_url: str, allow_private_network: bool) -> None:
    try:
        reject_secret_query_params(base_url)
        validate_service_url(base_url, allow_private_network)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _encrypt_credentials(
    auth_type: str,
    auth_config: dict,
    allow_private_network: bool = False,
    old_config: dict | None = None,
) -> str | None:
    try:
        config = dict(old_config or {})
        config.update(auth_config)
        validated = validate_auth_config(auth_type, config, allow_private_network)
        return encrypt_auth_config(validated) if validated else None
    except ValueError as exc:
        status_code = 503 if "MCP_AUTH_ENCRYPTION_KEY" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _decrypt_stored_config(encrypted: str | None) -> dict:
    """读取已存凭据；解密失败不能再冒成 500（与 _encrypt_credentials 保持同一套错误码）。"""
    try:
        return decrypt_auth_config(encrypted)
    except ValueError as exc:
        status_code = 503 if "MCP_AUTH_ENCRYPTION_KEY" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("", response_model=ApiServiceOut, status_code=201)
def create_api_service(payload: ApiServiceCreate, db: Session = Depends(get_db)):
    _validate_base_url(payload.base_url, payload.allow_private_network)
    if db.query(ApiService).filter(ApiService.name == payload.name).first():
        raise HTTPException(status_code=409, detail="API service name already exists")
    encrypted = _encrypt_credentials(
        payload.auth_type, payload.auth_config, payload.allow_private_network
    )
    service = ApiService(
        name=payload.name,
        base_url=payload.base_url,
        auth_type=payload.auth_type,
        auth_config_encrypted=encrypted,
        allow_private_network=payload.allow_private_network,
        request_timeout_seconds=payload.request_timeout_seconds,
        enabled=payload.enabled,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("", response_model=list[ApiServiceOut])
def list_api_services(db: Session = Depends(get_db)):
    return db.query(ApiService).order_by(ApiService.created_at.desc()).all()


@router.get("/{service_id}", response_model=ApiServiceOut)
def get_api_service(service_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_service_or_404(db, service_id)


@router.put("/{service_id}", response_model=ApiServiceOut)
def update_api_service(
    service_id: uuid.UUID,
    payload: ApiServiceUpdate,
    db: Session = Depends(get_db),
):
    service = _get_service_or_404(db, service_id)
    data = payload.model_dump(exclude_unset=True)
    base_url = data.get("base_url", service.base_url)
    allow_private = data.get("allow_private_network", service.allow_private_network)
    _validate_base_url(base_url, allow_private)
    auth_type = data.get("auth_type", service.auth_type)
    if "auth_type" in data or "auth_config" in data:
        old_config = (
            _decrypt_stored_config(service.auth_config_encrypted)
            if auth_type == service.auth_type
            else {}
        )
        service.auth_config_encrypted = _encrypt_credentials(
            auth_type, data.get("auth_config") or {}, allow_private, old_config
        )
        service.auth_type = auth_type
    if "name" in data:
        conflict = db.query(ApiService).filter(
            ApiService.name == data["name"], ApiService.id != service.id
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="API service name already exists")
        service.name = data["name"]
    service.base_url = base_url
    service.allow_private_network = allow_private
    if "request_timeout_seconds" in data:
        service.request_timeout_seconds = data["request_timeout_seconds"]
    if "enabled" in data:
        service.enabled = data["enabled"]
    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=204)
def delete_api_service(service_id: uuid.UUID, db: Session = Depends(get_db)):
    service = _get_service_or_404(db, service_id)
    db.query(Tool).filter(Tool.api_service_id == service.id).delete(synchronize_session=False)
    db.delete(service)
    db.commit()
    return None
