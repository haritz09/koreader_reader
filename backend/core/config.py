from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ebook Analyzer API"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ebook_analyzer"
    redis_url: str = "redis://localhost:6379"
    ebook_storage_path: str = "./data/ebooks"
    max_ebook_size_bytes: int = 10 * 1024 * 1024
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_fallback_models: str = "gemini-2.5-flash-lite"
    llm_provider: Literal["openai", "mock"] = "openai"
    allow_mock_llm: bool = False
    extraction_concurrency: int = 2
    extraction_max_attempts: int = 3
    extraction_retry_base_seconds: float = 1.0
    extraction_retry_max_seconds: float = 20.0
    extraction_requests_per_minute: int = 5
    extraction_batch_size: int = 3
    extraction_job_timeout_seconds: int = 3600
    embedding_provider: Literal["gemini", "mock"] = "gemini"
    embedding_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 100
    embedding_max_attempts: int = 3
    embedding_retry_base_seconds: float = 1.0
    embedding_retry_max_seconds: float = 20.0
    embedding_quota_defer_seconds: int = 21600
    allow_mock_embeddings: bool = False
    rag_build_stale_seconds: int = 7200
    community_resolution: float = 1.0
    community_max_levels: int = 3
    community_min_size: int = 4
    community_min_members: int = 2
    community_seed: int = 42
    community_fact_edge_weight: float = 2.0
    community_cooccurrence_edge_weight: float = 1.0

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
