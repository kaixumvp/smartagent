import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from scalar_fastapi import get_scalar_api_reference

from smartagent.api.middleware import rate_limit_middleware, trace_middleware
from smartagent.api.routes import (
    agents,
    auth,
    cost,
    evaluations,
    experiments,
    feedback,
    golden_sets,
    grants,
    memory,
    roles,
    runs,
    skills,
    tools,
    users,
)
from smartagent.config import get_settings
from smartagent.services.evaluation_service import sweep_interrupted

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str, trace_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "trace_id": trace_id}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Evaluation jobs live in-process, so a restart strands them. Close the books on startup
    # rather than leaving rows stuck in "running" forever. Best-effort, and skippable: a
    # database that is slow or unreachable must not hold up serving traffic.
    if settings.eval_sweep_on_startup:
        try:
            await sweep_interrupted()
        except Exception:  # noqa: BLE001
            logger.warning("could not sweep interrupted evaluations at startup", exc_info=True)
    yield
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SmartAgent",
        version="0.2.0",
        description="Single-agent multi-turn conversation + tool calling",
        lifespan=lifespan,
        docs_url=None,  # disable Swagger UI
        redoc_url=None,  # disable stock Redoc; Scalar served at /docs below
    )

    # Uniform middleware. Order: rate-limit added first, trace added last → trace is outermost,
    # so trace_id is assigned before rate limiting (and before any 429 is emitted).
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(trace_middleware)

    app.include_router(runs.router, prefix=settings.api_prefix)
    app.include_router(agents.router, prefix=settings.api_prefix)
    app.include_router(tools.router, prefix=settings.api_prefix)
    app.include_router(skills.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(roles.router, prefix=settings.api_prefix)
    app.include_router(users.router, prefix=settings.api_prefix)
    app.include_router(grants.router, prefix=settings.api_prefix)
    app.include_router(memory.router, prefix=settings.api_prefix)
    app.include_router(golden_sets.router, prefix=settings.api_prefix)
    app.include_router(evaluations.router, prefix=settings.api_prefix)
    app.include_router(experiments.router, prefix=settings.api_prefix)
    app.include_router(feedback.router, prefix=settings.api_prefix)
    app.include_router(cost.router, prefix=settings.api_prefix)

    @app.get("/docs", include_in_schema=False)
    async def docs():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=f"{app.title} · API Docs",
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            code = exc.detail.get("code", "INTERNAL_ERROR")
            message = exc.detail.get("message", str(exc.detail))
        else:
            code = "INTERNAL_ERROR"
            message = str(exc.detail)
        return _error_response(exc.status_code, code, message, getattr(request.state, "trace_id", None))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _error_response(400, "INVALID_ARGUMENT", str(exc.errors()), getattr(request.state, "trace_id", None))

    return app


app = create_app()
