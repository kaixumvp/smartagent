from functools import lru_cache

from fastapi import Depends, Request

from smartagent.adapters.pgvector_memory import VectorMemoryStore
from smartagent.config import Settings, get_settings
from smartagent.iam.permission_manager import PermissionManager
from ouroboros.llm.cost import CachingGateway
from ouroboros.llm.embedder import Embedder, HashEmbedder, LiteLLMEmbedder
from ouroboros.llm.litellm_gateway import LiteLLMGateway
from ouroboros.memory.consolidator import Consolidator
from ouroboros.memory.manager import MemoryManager
from ouroboros.memory.working import WorkingBrain
from ouroboros.tools.registry import ToolRegistry, build_default_registry


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return build_default_registry()


@lru_cache
def get_llm_gateway():
    """The shared gateway: LiteLLM, optionally behind a prompt cache.

    Tiered routing is NOT applied here — it is wrapped per run by `RunService` so the chosen
    model can be attributed to that run. That also fixes the cache-key ordering: the cache must
    sit *below* the router (`CachingGateway._key` includes the model, `ouroboros/llm/cost.py:23`),
    otherwise every routed call collides on the same empty-model key and an expensive-model
    answer gets served to a request that should have used the cheap one.
    """
    settings = get_settings()
    gateway = LiteLLMGateway(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        api_base=settings.llm_api_base,
    )
    if settings.llm_cache_enabled:
        return CachingGateway(gateway, max_size=settings.llm_cache_size)
    return gateway


@lru_cache
def get_judge_gateway() -> LiteLLMGateway:
    """Dedicated judge gateway: no cache, no routing.

    Scores must stay comparable across evaluations, so the judge model is fixed rather than
    chosen by a complexity classifier, and its cost is attributable separately from run cost.
    """
    settings = get_settings()
    return LiteLLMGateway(
        model=settings.judge_model or settings.llm_model,
        api_key=settings.judge_api_key or settings.deepseek_api_key,
        api_base=settings.judge_api_base or settings.llm_api_base,
    )


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_api_key:
        return LiteLLMEmbedder(
            settings.embedding_model,
            api_key=settings.embedding_api_key,
            api_base=settings.embedding_api_base,
        )
    return HashEmbedder(settings.embedding_dimension)


@lru_cache
def get_vector_store() -> VectorMemoryStore:
    return VectorMemoryStore(get_embedder())


@lru_cache
def get_permission_manager() -> PermissionManager:
    return PermissionManager()


def get_working_brain(request: Request) -> WorkingBrain:
    settings = get_settings()
    redis = request.app.state.redis
    return WorkingBrain(
        redis,
        window_size=settings.working_memory_window_size,
        ttl_seconds=settings.working_memory_ttl_seconds,
    )


def get_memory_manager(request: Request, settings: Settings = Depends(get_settings)) -> MemoryManager:
    redis = request.app.state.redis
    working = WorkingBrain(
        redis,
        window_size=settings.working_memory_window_size,
        ttl_seconds=settings.working_memory_ttl_seconds,
    )
    vector_store = get_vector_store()
    consolidator = Consolidator(vector_store, similarity_threshold=settings.consolidation_similarity_threshold)
    return MemoryManager(working, vector_store, consolidator)
