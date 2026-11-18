from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import get_retrieval, require_integration_key
from ..index import SearchFilter
from ..retrieval import RetrievalService

router = APIRouter(prefix="/v1", tags=["search"])

internal_router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _run_search(body: schemas.SearchRequest, db: Session, retrieval: RetrievalService) -> dict:
    flt = SearchFilter(
        kb_ids=body.kb_ids,
        folder_id=body.folder_id,
        mime_types=body.mime_types,
        created_after=body.created_after,
        created_before=body.created_before,
    )
    return retrieval.search(db, body.query, flt, top_k=body.top_k, rerank=body.rerank, mode=body.mode)


@router.post("/search", response_model=schemas.SearchResponse)
def search(
    body: schemas.SearchRequest,
    db: Session = Depends(get_db),
    retrieval: RetrievalService = Depends(get_retrieval),
):
    return _run_search(body, db, retrieval)


@internal_router.post(
    "/search",
    response_model=schemas.SearchResponse,
    dependencies=[Depends(require_integration_key)],
)
def internal_search(
    body: schemas.SearchRequest,
    db: Session = Depends(get_db),
    retrieval: RetrievalService = Depends(get_retrieval),
):
    return _run_search(body, db, retrieval)
