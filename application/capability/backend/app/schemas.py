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
    api_service_id: Optional[uuid.UUID] = None
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
    auth_type: str = "none"
    auth_config: dict[str, Any] = Field(default_factory=dict)
    credential_ref: Optional[str] = Field(default=None, max_length=255)


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    endpoint: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    auth_type: Optional[str] = None
    auth_config: Optional[dict[str, Any]] = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    endpoint: str
    auth_type: str = "none"
    has_authentication: bool = False
    status: str
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class SyncResult(BaseModel):
    synced: int
    missing: int
    provider_status: str


class ToolTestRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ApiServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    base_url: str = Field(..., min_length=1, max_length=2048)
    auth_type: str = "none"
    auth_config: dict[str, Any] = Field(default_factory=dict)
    allow_private_network: bool = False
    request_timeout_seconds: int = Field(default=30, ge=1, le=120)
    enabled: bool = True


class ApiServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    auth_type: Optional[str] = None
    auth_config: Optional[dict[str, Any]] = None
    allow_private_network: Optional[bool] = None
    request_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    enabled: Optional[bool] = None


class ApiServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_url: str
    auth_type: str
    has_authentication: bool
    allow_private_network: bool
    request_timeout_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ApiToolCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    lifecycle_state: LifecycleState = LifecycleState.draft
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    api_service_id: uuid.UUID
    method: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    path: str = Field(..., min_length=1, max_length=2048)
    query_template: dict[str, Any] = Field(default_factory=dict)
    header_template: dict[str, Any] = Field(default_factory=dict)
    body_template: Any = None
