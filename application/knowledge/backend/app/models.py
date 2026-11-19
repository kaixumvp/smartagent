from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .ids import utcnow


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    folders: Mapped[list["Folder"]] = relationship(back_populates="knowledge_base")
    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base")


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="folders")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    parser_name: Mapped[str] = mapped_column(String(64), default="")
    ocr_used: Mapped[int] = mapped_column(Integer, default=0)
    original_key: Mapped[str] = mapped_column(String(512), default="")
    markdown_key: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    folder_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[str] = mapped_column(String(512), default="")
    start_offset: Mapped[int] = mapped_column(Integer, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="ingest")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
