import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .database import Base
from .mcp_auth import decrypt_auth_config, summarize_auth_config


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

    @property
    def auth_config_summary(self) -> dict:
        """认证配置回显：非敏感字段原样给出，密钥只给“是否已配置”和形态信息。

        解密失败不能污染列表接口，这里吞掉异常只回一条说明。
        """
        if not self.auth_config_encrypted:
            return {}
        try:
            config = decrypt_auth_config(self.auth_config_encrypted)
        except ValueError:
            return {"error": "stored credentials cannot be decrypted; re-save them"}
        return summarize_auth_config(self.auth_type, config)


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


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=False)
    active_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version_no", name="uq_workflow_versions_number"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    version_no = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    revision = Column(Integer, nullable=False, default=1)
    definition = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "idempotency_key", name="uq_workflow_run_idempotency"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    workflow_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=False)
    status = Column(String(32), nullable=False, default="queued")
    idempotency_key = Column(String(255), nullable=True)
    input_data = Column(JSONB, nullable=False, default=dict)
    context = Column(JSONB, nullable=False, default=dict)
    output = Column(JSONB, nullable=True)
    error = Column(JSONB, nullable=True)
    current_node_id = Column(String(100), nullable=True)
    correlation_id = Column(String(255), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowNodeRun(Base):
    __tablename__ = "workflow_node_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id = Column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(String(100), nullable=False)
    status = Column(String(32), nullable=False)
    input_data = Column(JSONB, nullable=True)
    output = Column(JSONB, nullable=True)
    error = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowInteraction(Base):
    __tablename__ = "workflow_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id = Column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="open")
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False, default="")
    form_schema = Column(JSONB, nullable=False, default=dict)
    display_data = Column(JSONB, nullable=False, default=dict)
    response = Column(JSONB, nullable=True)
    response_comment = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    resume_context = Column(JSONB, nullable=False, default=dict)
