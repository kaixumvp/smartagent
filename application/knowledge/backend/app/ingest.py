from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .chunking import chunk_markdown
from .config import settings
from .embedding import Embedder
from .ids import new_id, utcnow
from .index import VectorIndex, VectorItem
from .parse import OcrEngine, ParseResult, parse_bytes
from .storage import ObjectStore


def enqueue_ingest(db: Session, document_id: str, kind: str = "ingest") -> models.ProcessingJob:
    job = models.ProcessingJob(id=new_id("job"), document_id=document_id, kind=kind, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_next_job(
    db: Session,
    store: ObjectStore,
    embedder: Embedder,
    index: VectorIndex,
    ocr: OcrEngine,
) -> bool:
    job = (
        db.query(models.ProcessingJob)
        .filter(models.ProcessingJob.status == "queued")
        .order_by(models.ProcessingJob.created_at.asc())
        .first()
    )
    if job is None:
        return False
    job.status = "running"
    job.started_at = utcnow()
    db.commit()
    try:
        ingest_document(db, store, embedder, index, ocr, job.document_id)
        job.status = "succeeded"
        job.finished_at = utcnow()
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = utcnow()
        doc = db.get(models.Document, job.document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = str(exc)
            doc.updated_at = utcnow()
        db.commit()
    return True


def ingest_document(
    db: Session,
    store: ObjectStore,
    embedder: Embedder,
    index: VectorIndex,
    ocr: OcrEngine,
    document_id: str,
) -> ParseResult:
    doc = db.get(models.Document, document_id)
    if doc is None:
        raise ValueError(f"document not found: {document_id}")
    doc.status = "processing"
    doc.updated_at = utcnow()
    db.commit()

    raw = store.get(doc.original_key)
    parsed = parse_bytes(doc.filename, doc.content_type, raw, ocr)
    markdown_key = f"parsed/{doc.knowledge_base_id}/{doc.id}.md"
    store.put(markdown_key, parsed.markdown.encode("utf-8"))
    doc.markdown_key = markdown_key
    doc.parser_name = parsed.parser_name
    doc.ocr_used = 1 if parsed.ocr_used else 0

    db.query(models.Chunk).filter(models.Chunk.document_id == doc.id).delete()
    index.delete_document(doc.id)

    drafts = chunk_markdown(parsed.markdown, settings.max_chunk_chars, settings.chunk_overlap)
    vectors = embedder.embed([d.text for d in drafts]) if drafts else []
    items: list[VectorItem] = []
    for i, draft in enumerate(drafts):
        chunk = models.Chunk(
            id=new_id("chunk"),
            document_id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            folder_id=doc.folder_id,
            ordinal=i,
            text=draft.text,
            heading_path=draft.heading_path,
            start_offset=draft.start_offset,
            end_offset=draft.end_offset,
            content_type=doc.content_type,
        )
        db.add(chunk)
        items.append(
            VectorItem(
                chunk_id=chunk.id,
                document_id=doc.id,
                knowledge_base_id=doc.knowledge_base_id,
                folder_id=doc.folder_id,
                content_type=doc.content_type,
                created_at=doc.created_at or utcnow(),
                vector=vectors[i],
            )
        )
    db.flush()
    index.upsert(items)
    doc.status = "ready"
    doc.error = ""
    doc.updated_at = utcnow()
    db.commit()
    return parsed
