from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_embedder, get_index, get_ocr, get_store
from ..ingest import process_next_job

router = APIRouter(prefix="/v1", tags=["jobs"])

# Cap how many jobs a single tick drains so a malformed document cannot wedge the worker.
MAX_JOBS_PER_TICK = 100


@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/jobs/process")
def process_jobs(
    db: Session = Depends(get_db),
    store=Depends(get_store),
    embedder=Depends(get_embedder),
    index=Depends(get_index),
    ocr=Depends(get_ocr),
):
    """Run one drain tick synchronously (demo / test helper; the worker does this in a loop)."""
    processed = 0
    while processed < MAX_JOBS_PER_TICK and process_next_job(db, store, embedder, index, ocr):
        processed += 1
    return {"processed": processed}
