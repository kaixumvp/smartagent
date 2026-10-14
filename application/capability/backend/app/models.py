import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .database import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    endpoint = Column(String(2048), nullable=False)
    credential_ref = Column(String(255), nullable=True)
    auth_type = Column(String(40), nullable=False, default="none")
    auth_config_encrypted = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="offline")  # online / offline
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def has_credential(self) -> bool:
        """Exposed instead of `credential_ref` itself — the API never echoes the ref back."""
        return bool(self.credential_ref)

    @property
    def has_authentication(self) -> bool:
        return self.auth_type != "none" and bool(self.auth_config_encrypted)


class ApiService(Base):
    __tablename__ = "api_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    base_url = Column(String(2048), nullable=False)
    auth_type = Column(String(40), nullable=False, default="none")
    auth_config_encrypted = Column(Text, nullable=True)
    allow_private_network = Column(Boolean, nullable=False, default=False)
    request_timeout_seconds = Column(Integer, nullable=False, default=30)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def has_authentication(self) -> bool:
        return self.auth_type != "none" and bool(self.auth_config_encrypted)


class Tool(Base):
    __tablename__ = "tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(20), nullable=False, default="local")  # local / mcp / api
    provider_id = Column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    api_service_id = Column(
        UUID(as_uuid=True), ForeignKey("api_services.id", ondelete="CASCADE"), nullable=True
    )
    remote_tool_name = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    lifecycle_state = Column(String(20), nullable=False, default="draft")  # draft / active / remote_missing
    enabled = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    manifest = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
