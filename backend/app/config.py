from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./library.db"
    app_env: str = "development"
    auth0_domain: str = ""
    auth0_audience: str = ""
    auth_disable_jwt_verification: bool = True
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    ai_rag_top_k: int = 5
    ai_chat_memory_turns: int = 8
    ai_chat_session_ttl_minutes: int = 180
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
