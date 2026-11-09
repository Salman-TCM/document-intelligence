from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel"
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 200
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # When set, every request must send it in the X-API-Key header.
    api_key: str | None = None

    # Without an Anthropic key the rule-based extractor is used instead of the LLM.
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"

    ocr_workers: int = 4
    # Tests and the eval script run jobs in-process instead of through Redis.
    run_jobs_inline: bool = False


settings = Settings()
