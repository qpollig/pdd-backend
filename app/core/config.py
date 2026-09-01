from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "PDD Test Platform API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    # Database
    DATABASE_URL: PostgresDsn = "postgresql+asyncpg://pdd:pdd@localhost:5432/pdd"

    # JWT / Auth
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PROD"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # OAuth providers
    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    VK_CLIENT_ID: str = ""
    VK_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_URI: str = "https://app.example.com/oauth/callback"

    # Gameplay / freemium
    DEFAULT_LIVES_MAX: int = 5
    LIVES_RESET_HOUR_UTC: int = 0  # 00:00 UTC daily reset

    # Exam rules (gibdd_exam mode)
    EXAM_BASE_QUESTIONS: int = 20  # тикет из 20 вопросов (стандарт ГИБДД)
    EXAM_EXTRA_QUESTIONS_PER_ERROR: int = 5
    EXAM_MAX_ERRORS_ALLOWED: int = 2
    EXAM_MAX_EXTRA_QUESTIONS: int = 10

    # Billing
    TRIAL_PRICE_RUB: int = 1
    TRIAL_PERIOD_DAYS: int = 3
    SUBSCRIPTION_PRICE_RUB: int = 299
    SUBSCRIPTION_PERIOD_DAYS: int = 30

    ACQUIRER_PROVIDER: str = "yookassa"  # yookassa | tbank
    ACQUIRER_SHOP_ID: str = ""
    ACQUIRER_SECRET_KEY: str = ""
    ACQUIRER_WEBHOOK_SECRET: str = ""

    BILLING_WORKER_INTERVAL_MINUTES: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
