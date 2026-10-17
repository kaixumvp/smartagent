from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mcp_auth_encryption_key: str | None = None
    capability_integration_key: str | None = None

    database_url: str = "postgresql+psycopg2://registry:registry@localhost:5432/registry"
    # MVP 便利项：启动时自动建表；正式迁移请用 alembic upgrade head
    auto_create_tables: bool = True

    # 访问令牌（OAuth2 / bearer 自动获取）的 Redis 缓存；连不上时自动降级为每次现取
    redis_url: str = "redis://localhost:6380/0"
    token_cache_enabled: bool = True

    # 打印 API Tool 的出站 HTTP 请求/响应日志（URL、header、body）；凭据按名称自动脱敏
    api_tool_http_log: bool = True


settings = Settings()
