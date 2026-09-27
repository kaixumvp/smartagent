from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "smartagent"
    api_prefix: str = "/v1"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://smartagent:smartagent@localhost:5432/smartagent"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    llm_api_base: str | None = None

    # Embedding (V0.2 long-term memory)
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_api_base: str | None = None
    embedding_dimension: int = 1536  # Must match the vector() column dimension in the DB.

    # Auth (V0.2 JWT)
    auth_enabled: bool = True
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_seconds: int = 3600

    # Rate limiting (token bucket over Redis)
    rate_limit_enabled: bool = True
    rate_limit_per_min: int = 60
    rate_limit_burst: int = 120

    # Runtime defaults
    max_iterations: int = 20
    timeout_seconds: int = 120
    max_subagent_depth: int = 3

    # Memory
    working_memory_window_size: int = 20
    working_memory_ttl_seconds: int = 24 * 3600
    memory_recall_top_k: int = 5
    consolidation_similarity_threshold: float = 0.85

    # Judge (V1.1 evaluation). Kept separate from the business LLM so the scoring model can
    # differ from the model under test, and so judging cost is attributable on its own.
    judge_model: str = ""  # empty → falls back to llm_model
    judge_api_key: str = ""  # empty → falls back to deepseek_api_key
    judge_api_base: str | None = None

    # LLM cache + tiered routing (V1.1 cost)
    llm_cache_enabled: bool = False
    llm_cache_size: int = 256
    llm_routing_enabled: bool = False
    llm_cheap_model: str = ""
    llm_expensive_model: str = ""
    llm_routing_threshold: int = 2000  # total message length above which the task is "complex"

    # Evaluation
    eval_concurrency: int = 2  # cases in flight; each holds its own DB session
    # Sweep evaluations stranded by a restart. Disable where startup must not touch the
    # database (tests, or a deployment that runs the sweep as a separate job).
    eval_sweep_on_startup: bool = True

    # Cost: {"model": [input_per_1k, output_per_1k]} overriding src.pricing defaults.
    model_prices: dict[str, list[float]] = {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
