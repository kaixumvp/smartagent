import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LifecycleState(str, Enum):
    draft = "draft"
    active = "active"
    remote_missing = "remote_missing"


class ProviderStatus(str, Enum):
    online = "online"
    offline = "offline"


class ToolCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    lifecycle_state: LifecycleState = LifecycleState.draft
    version: str = "1.0.0"
    tags: list[str] = []
    keywords: list[str] = []
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    enabled: bool = True


class ToolUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    lifecycle_state: Optional[LifecycleState] = None
    version: Optional[str] = None
    tags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    provider_id: Optional[uuid.UUID]
    remote_tool_name: Optional[str]
    display_name: str
    description: str
    lifecycle_state: str
    enabled: bool
    last_synced_at: Optional[datetime]
    manifest: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    endpoint: str = Field(..., min_length=1, max_length=2048)
    credential_ref: Optional[str] = Field(default=None, max_length=255)


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    endpoint: str
    credential_ref: Optional[str]
    status: str
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class SyncResult(BaseModel):
    synced: int
    missing: int
    provider_status: str
