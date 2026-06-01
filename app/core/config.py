from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://ptc:ptc_secret@localhost:5432/ptc_alcaldias"

    JWT_SECRET_KEY: str = "change-me-to-a-random-64-char-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    APP_ENV: str = "development"

    LOGIN_RATE_LIMIT: str = "5/15minutes"

    # ── Agente Institucional · Motor LLM ──────────────────────────────────
    # Proveedor activo: "deepseek" (por defecto) | "anthropic" | "fake" (tests)
    LLM_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # Para migrar a Claude basta con LLM_PROVIDER=anthropic + esta key.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 1500

    # ── Agente Institucional · RAG ────────────────────────────────────────
    # Base vectorial local (ChromaDB persistente).
    VECTOR_DB_PATH: str = "./data/chroma"
    # Embeddings locales (sentence-transformers). DeepSeek no ofrece embeddings.
    # Proveedor: "local" (sentence-transformers) | "fake" (determinista, tests/offline).
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    # Documentos demo a ingestar.
    KNOWLEDGE_PATH: str = "./data/seed/knowledge"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
