from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_index, get_store
from ..ids import new_id, utcnow
from ..ingest import enqueue_ingest

router = APIRouter(prefix="/v1", tags=["documents"])


def _kb_or_404(db: Session, kb_id: str) -> models.KnowledgeBase:
    kb = db.get(models.KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return kb


def _doc_or_404(db: Session, document_id: str) -> models.Document:
    doc = db.get(models.Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.post("/knowledge-bases/{kb_id}/documents", response_model=schemas.DocumentOut, status_code=201)
def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    folder_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    store=Depends(get_store),
):
    kb = _kb_or_404(db, kb_id)
    if folder_id:
        folder = db.get(models.Folder, folder_id)
        if folder is None or folder.knowledge_base_id != kb_id:
            raise HTTPException(status_code=404, detail="folder not found")

    filename = Path(file.filename or "unnamed").name or "unnamed"
    content = file.file.read()

    document = models.Document(
        id=new_id("doc"),
        knowledge_base_id=kb.id,
        folder_id=folder_id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        status="pending",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    original_key = f"originals/{kb.id}/{document.id}/{filename}"
    store.put(original_key, content)
    document.original_key = original_key

    db.add(document)
    db.commit()
    db.refresh(document)
    enqueue_ingest(db, document.id)
    return document


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[schemas.DocumentOut])
def list_documents(
    kb_id: str,
    folder_id: str | None = None,
    db: Session = Depends(get_db),
):
    _kb_or_404(db, kb_id)
    q = db.query(models.Document).filter(models.Document.knowledge_base_id == kb_id)
    if folder_id:
        q = q.filter(models.Document.folder_id == folder_id)
    return q.order_by(models.Document.created_at.desc()).all()


@router.get("/documents/{document_id}", response_model=schemas.DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    return _doc_or_404(db, document_id)


@router.get("/documents/{document_id}/download")
def download_original(
    document_id: str,
    db: Session = Depends(get_db),
    store=Depends(get_store),
):
    doc = _doc_or_404(db, document_id)
    data = store.get(doc.original_key)
    return Response(
        content=data,
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.get("/documents/{document_id}/markdown")
def download_markdown(
    document_id: str,
    db: Session = Depends(get_db),
    store=Depends(get_store),
):
    doc = _doc_or_404(db, document_id)
    if not doc.markdown_key:
        raise HTTPException(status_code=404, detail="document not processed yet")
    return Response(content=store.get(doc.markdown_key), media_type="text/markdown")


@router.post("/documents/{document_id}/reingest", response_model=schemas.JobOut)
def reingest_document(document_id: str, db: Session = Depends(get_db)):
    doc = _doc_or_404(db, document_id)
    doc.status = "pending"
    doc.error = ""
    doc.updated_at = utcnow()
    db.commit()
    return enqueue_ingest(db, document_id, kind="reingest")


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    store=Depends(get_store),
    index=Depends(get_index),
):
    doc = _doc_or_404(db, document_id)
    db.query(models.Chunk).filter(models.Chunk.document_id == document_id).delete()
    db.query(models.ProcessingJob).filter(models.ProcessingJob.document_id == document_id).delete()
    index.delete_document(document_id)
    if doc.original_key:
        store.delete(doc.original_key)
    if doc.markdown_key:
        store.delete(doc.markdown_key)
    db.delete(doc)
    db.commit()
    return {"ok": True}


@router.get("/documents/{document_id}/jobs", response_model=list[schemas.JobOut])
def list_document_jobs(document_id: str, db: Session = Depends(get_db)):
    _doc_or_404(db, document_id)
    return (
        db.query(models.ProcessingJob)
        .filter(models.ProcessingJob.document_id == document_id)
        .order_by(models.ProcessingJob.created_at.desc())
        .all()
    )
