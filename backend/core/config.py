from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ebook Analyzer API"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ebook_analyzer"
    redis_url: str = "redis://localhost:6379"
    ebook_storage_path: str = "./data/ebooks"
    max_ebook_size_bytes: int = 10 * 1024 * 1024
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"

    jwt_secret: str = "dev-insecure-secret-change-me-use-a-real-one"
    jwt_algorithm: str = "HS256"
    jwt_ttl_days: int = 365
    session_cookie_name: str = "koreader_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_rate_limit: int = 10
    session_rate_limit_window_seconds: int = 60
    trust_forwarded_for: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
