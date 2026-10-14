import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..manifest import manifest_from_mcp_tool
from ..mcp_auth import decrypt_auth_config, encrypt_auth_config, reject_secret_query_params, validate_auth_config
from ..mcp_client import describe_mcp_error, list_remote_tools
from ..models import Provider, Tool
from ..schemas import ProviderCreate, ProviderOut, ProviderUpdate, SyncResult

router = APIRouter(prefix="/providers", tags=["providers"])


def _get_provider_or_404(db: Session, provider_id: uuid.UUID) -> Provider:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.post("", response_model=ProviderOut, status_code=201)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    try:
        reject_secret_query_params(payload.endpoint)
        auth_config = validate_auth_config(payload.auth_type, payload.auth_config)
        encrypted_config = encrypt_auth_config(auth_config)
    except ValueError as exc:
        status_code = 503 if "MCP_AUTH_ENCRYPTION_KEY" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    provider = Provider(
        name=payload.name,
        endpoint=payload.endpoint,
        auth_type=payload.auth_type,
        auth_config_encrypted=encrypted_config,
        credential_ref=payload.credential_ref,
        status="offline",
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    return db.query(Provider).order_by(Provider.created_at.desc()).all()


@router.get("/{provider_id}", response_model=ProviderOut)
def get_provider(provider_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_provider_or_404(db, provider_id)


@router.put("/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
):
    provider = _get_provider_or_404(db, provider_id)
    data = payload.model_dump(exclude_unset=True)
    endpoint = data.get("endpoint", provider.endpoint)
    auth_type = data.get("auth_type", provider.auth_type)
    try:
        reject_secret_query_params(endpoint)
        if "auth_type" in data or "auth_config" in data:
            old_config = (
                decrypt_auth_config(provider.auth_config_encrypted)
                if auth_type == provider.auth_type
                else {}
            )
            old_config.update(data.get("auth_config") or {})
            auth_config = validate_auth_config(auth_type, old_config)
            provider.auth_config_encrypted = encrypt_auth_config(auth_config)
            provider.auth_type = auth_type
    except ValueError as exc:
        status_code = 503 if "MCP_AUTH_ENCRYPTION_KEY" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if "name" in data:
        provider.name = data["name"]
    provider.endpoint = endpoint
    provider.status = "offline"
    db.commit()
    db.refresh(provider)
    return provider


@router.post("/{provider_id}/sync", response_model=SyncResult)
def sync_provider(provider_id: uuid.UUID, db: Session = Depends(get_db)):
    provider = _get_provider_or_404(db, provider_id)

    # 同步 endpoint 是 def（线程池运行），此处无事件循环，用 asyncio.run 连接 MCP
    try:
        auth_config = decrypt_auth_config(provider.auth_config_encrypted)
        remote_tools = asyncio.run(
            list_remote_tools(provider.endpoint, provider.auth_type, auth_config)
        )
    except Exception as exc:  # noqa: BLE001  连接/超时/协议错误统一视为 offline
        provider.status = "offline"
        provider.last_sync_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"MCP 连接失败: {describe_mcp_error(exc)}",
        ) from exc

    now = datetime.now(timezone.utc)
    remote_names: set[str] = set()

    # Upsert：按 (provider_id, remote_tool_name) 更新或新建
    for rt in remote_tools:
        name = rt["name"]
        remote_names.add(name)
        manifest = manifest_from_mcp_tool(provider, rt)
        display_name = rt.get("title") or name
        existing = (
            db.query(Tool)
            .filter(Tool.provider_id == provider.id, Tool.remote_tool_name == name)
            .first()
        )
        if existing is not None:
            existing.description = rt["description"]
            existing.display_name = display_name
            existing.manifest = manifest
            existing.last_synced_at = now
            if existing.lifecycle_state == "remote_missing":
                existing.lifecycle_state = "draft"
        else:
            db.add(
                Tool(
                    source="mcp",
                    provider_id=provider.id,
                    remote_tool_name=name,
                    display_name=display_name,
                    description=rt["description"],
                    lifecycle_state="draft",
                    enabled=True,
                    last_synced_at=now,
                    manifest=manifest,
                )
            )

    # 远端删除检测：该 provider 下 source=mcp 且不在本次列表中的 Tool 标记 remote_missing
    missing_count = 0
    registered = db.query(Tool).filter(Tool.provider_id == provider.id, Tool.source == "mcp").all()
    for tool in registered:
        if tool.remote_tool_name not in remote_names:
            tool.lifecycle_state = "remote_missing"
            missing_count += 1

    provider.status = "online"
    provider.last_sync_at = now
    db.commit()

    return SyncResult(synced=len(remote_tools), missing=missing_count, provider_status=provider.status)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: uuid.UUID, db: Session = Depends(get_db)):
    provider = _get_provider_or_404(db, provider_id)
    db.query(Tool).filter(
        Tool.provider_id == provider.id,
        Tool.source == "mcp",
    ).delete(synchronize_session=False)
    db.delete(provider)
    db.commit()
    return None
