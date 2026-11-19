from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (PostgreSQL in production, SQLite for local dev / tests)
    database_url: str = "sqlite:///./data/knowledge.db"
    auto_create_tables: bool = True

    # Object storage: "local" (filesystem dir) or "s3" (S3-compatible, e.g. MinIO)
    object_store_type: str = "local"
    object_store_dir: str = "./data/objects"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "knowledge"
    s3_secure: bool = False

    # Vector index: empty qdrant_url → in-memory index (dev/tests); set to http://qdrant:6333 in compose
    qdrant_url: str = ""
    qdrant_collection: str = "knowledge_chunks"

    # Embedding: "hash" (dependency-free, deterministic) or "http" (OpenAI-compatible endpoint)
    embedder: str = "hash"
    embedding_dim: int = 256
    embedding_url: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""

    # OCR: "none" or "tesseract" (needs the `ocr` extra: pytesseract + pillow + system tesseract)
    ocr_backend: str = "none"
    ocr_lang: str = "chi_sim+eng"

    # Reranker: "lexical" (dependency-free) or "http" (cross-encoder endpoint)
    reranker_backend: str = "lexical"
    reranker_url: str = ""
    reranker_model: str = ""

    # Internal Retrieve API shared key; empty disables the check (MVP-friendly, like Capability)
    integration_key: str = ""

    # Chunking / retrieval knobs
    max_chunk_chars: int = 800
    chunk_overlap: int = 120
    search_candidate_multiplier: int = 4
    rerank_enabled: bool = True
    context_max_chars: int = 6000

    # Background ingest worker
    worker_enabled: bool = True
    worker_interval_seconds: float = 0.5


settings = Settings()
