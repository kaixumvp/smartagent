from fastapi import Header, HTTPException, Request

from .config import settings
from .embedding import Embedder
from .index import VectorIndex
from .parse import OcrEngine
from .retrieval import RetrievalService
from .storage import ObjectStore


def get_store(request: Request) -> ObjectStore:
    return request.app.state.store


def get_index(request: Request) -> VectorIndex:
    return request.app.state.index


def get_embedder(request: Request) -> Embedder:
    return request.app.state.embedder


def get_ocr(request: Request) -> OcrEngine:
    return request.app.state.ocr


def get_retrieval(request: Request) -> RetrievalService:
    return request.app.state.retrieval


def require_integration_key(x_integration_key: str | None = Header(default=None)) -> None:
    if not settings.integration_key:
        return
    if x_integration_key != settings.integration_key:
        raise HTTPException(status_code=401, detail="invalid integration key")
