from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..ids import new_id, utcnow

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge-bases"])


def _kb_or_404(db: Session, kb_id: str) -> models.KnowledgeBase:
    kb = db.get(models.KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")
    return kb


@router.post("", response_model=schemas.KnowledgeBaseOut)
def create_kb(body: schemas.KnowledgeBaseCreate, db: Session = Depends(get_db)):
    kb = models.KnowledgeBase(id=new_id("kb"), name=body.name, description=body.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("", response_model=list[schemas.KnowledgeBaseOut])
def list_kbs(db: Session = Depends(get_db)):
    return db.query(models.KnowledgeBase).order_by(models.KnowledgeBase.created_at.desc()).all()


@router.get("/{kb_id}", response_model=schemas.KnowledgeBaseOut)
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    return _kb_or_404(db, kb_id)


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = _kb_or_404(db, kb_id)
    db.query(models.Chunk).filter(models.Chunk.knowledge_base_id == kb_id).delete()
    db.query(models.Document).filter(models.Document.knowledge_base_id == kb_id).delete()
    db.query(models.Folder).filter(models.Folder.knowledge_base_id == kb_id).delete()
    db.delete(kb)
    db.commit()
    return {"ok": True}


@router.post("/{kb_id}/folders", response_model=schemas.FolderOut)
def create_folder(kb_id: str, body: schemas.FolderCreate, db: Session = Depends(get_db)):
    _kb_or_404(db, kb_id)
    if body.parent_id:
        parent = db.get(models.Folder, body.parent_id)
        if parent is None or parent.knowledge_base_id != kb_id:
            raise HTTPException(status_code=404, detail="parent folder not found")
    folder = models.Folder(
        id=new_id("folder"),
        knowledge_base_id=kb_id,
        parent_id=body.parent_id,
        name=body.name,
        created_at=utcnow(),
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.get("/{kb_id}/folders", response_model=list[schemas.FolderOut])
def list_folders(kb_id: str, db: Session = Depends(get_db)):
    _kb_or_404(db, kb_id)
    return (
        db.query(models.Folder)
        .filter(models.Folder.knowledge_base_id == kb_id)
        .order_by(models.Folder.created_at.asc())
        .all()
    )
