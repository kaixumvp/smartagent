from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://registry:registry@localhost:5432/registry"
    # MVP 便利项：启动时自动建表；正式迁移请用 alembic upgrade head
    auto_create_tables: bool = True


settings = Settings()
