import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  注册模型
from .config import settings
from .database import Base, SessionLocal, engine
from .embedding import build_embedder
from .index import build_index
from .ingest import process_next_job
from .parse import build_ocr
from .retrieval import RetrievalService, build_reranker
from .routers import bases, documents, jobs, search
from .storage import build_store

logger = logging.getLogger("app")

MAX_JOBS_PER_TICK = 100


def _configure_logging() -> None:
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    logging.getLogger("httpx").setLevel(logging.WARNING)


_configure_logging()


def build_components():
    store = build_store()
    embedder = build_embedder(settings.embedder, settings.embedding_dim, settings.embedding_url, settings.embedding_model, settings.embedding_api_key)
    ocr = build_ocr(settings.ocr_backend)
    index = build_index(settings.qdrant_url, settings.qdrant_collection, embedder.dim)
    reranker = build_reranker(settings.reranker_backend, settings.reranker_url, settings.reranker_model)
    retrieval = RetrievalService(
        embedder,
        index,
        reranker=reranker,
        candidate_multiplier=settings.search_candidate_multiplier,
        rerank_enabled=settings.rerank_enabled,
        context_max_chars=settings.context_max_chars,
    )
    return store, embedder, ocr, index, retrieval


def _drain_jobs(app: FastAPI) -> int:
    db = SessionLocal()
    try:
        processed = 0
        while processed < MAX_JOBS_PER_TICK and process_next_job(
            db, app.state.store, app.state.embedder, app.state.index, app.state.ocr
        ):
            processed += 1
        return processed
    finally:
        db.close()


async def _worker_loop(app: FastAPI) -> None:
    while True:
        try:
            await asyncio.to_thread(_drain_jobs, app)
        except Exception:
            logger.exception("Ingest worker cycle failed")
        await asyncio.sleep(settings.worker_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)

    store, embedder, ocr, index, retrieval = build_components()
    app.state.store = store
    app.state.embedder = embedder
    app.state.ocr = ocr
    app.state.index = index
    app.state.retrieval = retrieval

    worker = asyncio.create_task(_worker_loop(app)) if settings.worker_enabled else None
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    app = FastAPI(title="Knowledge Hub", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(bases.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(search.internal_router)
    app.include_router(jobs.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
