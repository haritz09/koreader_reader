from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ebook Analyzer API"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ebook_analyzer"
    redis_url: str = "redis://localhost:6379"
    ebook_storage_path: str = "./data/ebooks"
    max_ebook_size_bytes: int = 50 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
