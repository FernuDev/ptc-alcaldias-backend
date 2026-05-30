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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
