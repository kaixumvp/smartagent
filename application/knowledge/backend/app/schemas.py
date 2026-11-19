from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FolderCreate(BaseModel):
    name: str
    parent_id: str | None = None


class FolderOut(BaseModel):
    id: str
    knowledge_base_id: str
    parent_id: str | None
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: str
    knowledge_base_id: str
    folder_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    status: str
    parser_name: str
    ocr_used: bool
    error: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    document_id: str
    kind: str
    status: str
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str
    kb_ids: list[str] = Field(default_factory=list)
    top_k: int = 8
    folder_id: str | None = None
    mime_types: list[str] = Field(default_factory=list)
    created_after: datetime | None = None
    created_before: datetime | None = None
    rerank: bool = True
    # "hybrid" (default) | "vector" | "keyword" — explicit override for A/B comparison
    mode: str = "hybrid"


class ChunkHit(BaseModel):
    id: str
    document_id: str
    knowledge_base_id: str
    folder_id: str | None
    filename: str
    heading_path: str
    text: str
    start_offset: int
    end_offset: int
    dense_score: float
    sparse_score: float
    fused_score: float
    rerank_score: float
    evidence: dict


class QueryAnalysisOut(BaseModel):
    query: str
    terms: list[str]
    quoted: list[str]
    strategy: str


class SearchResponse(BaseModel):
    query: str
    analysis: QueryAnalysisOut
    mode: str
    rerank_applied: bool
    chunks: list[ChunkHit]
    context: str
