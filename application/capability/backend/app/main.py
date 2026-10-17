import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from . import models  # noqa: F401  注册模型
from .routers import api_services, api_tools, internal, providers, tools, workflows
from .workflow_engine import expire_due_interactions, process_queued_workflow_runs

logger = logging.getLogger(__name__)


def _configure_app_logging() -> None:
    """uvicorn 只配置自己的 logger，业务 logger 默认没有 handler，INFO 会被直接丢弃。"""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    # httpx 的 INFO 日志会原样打印请求 URL；api_key_query 认证把密钥放在 query 里，
    # 会被它连值一起输出，所以只放行 WARNING 及以上。
    logging.getLogger("httpx").setLevel(logging.WARNING)


_configure_app_logging()


def _process_workflow_jobs() -> None:
    db = SessionLocal()
    try:
        expire_due_interactions(db)
        process_queued_workflow_runs(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    expiry_task = asyncio.create_task(_workflow_expiry_loop())
    try:
        yield
    finally:
        expiry_task.cancel()
        try:
            await expiry_task
        except asyncio.CancelledError:
            pass


async def _workflow_expiry_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_process_workflow_jobs)
        except Exception:
            logger.exception("Workflow worker cycle failed")
        await asyncio.sleep(10)


app = FastAPI(title="Capability Registry", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tools.router)
app.include_router(providers.router)
app.include_router(api_services.router)
app.include_router(api_tools.router)
app.include_router(internal.router)
app.include_router(workflows.router)


@app.get("/health")
def health():
    return {"status": "ok"}
