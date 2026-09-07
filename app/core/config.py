from functools import lru_cache

from pydantic import PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ENVIRONMENT-значения, при которых допустимы дефолт-заглушки секретов (локальная разработка,
# тесты, CI). Всё остальное (dev, staging, production) считается «развёрнутым» окружением,
# где заглушки запрещены.
_LOCAL_ENVIRONMENTS = {"local", "test", "ci"}
_PLACEHOLDER_JWT_SECRETS = {"", "CHANGE_ME_IN_PROD"}


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "PDD Test Platform API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    # CORS — список источников фронтенда, которым браузер разрешит обращаться к API.
    # Comma-separated ("https://app.dev.example.ru,https://admin.dev.example.ru") либо "*" для любого.
    # На dev-сервере фронтенд ходит из браузера с другого домена — без этого все запросы
    # блокируются CORS-ошибкой. Аутентификация у нас по Bearer-токену (не cookie), поэтому
    # "*" безопасно сочетается с allow_credentials=False (см. app/main.py).
    CORS_ALLOW_ORIGINS: str = "*"

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
    # Dev-only: разрешает вход через OAuth без зарегистрированных приложений Yandex/VK.
    # Когда True И у провайдера не заданы CLIENT_ID/SECRET — вместо реального обращения к
    # oauth.yandex.ru / oauth.vk.com backend возвращает детерминированный фейковый профиль
    # (по одному коду — один и тот же пользователь). Никогда не включать в production.
    OAUTH_ALLOW_MOCK: bool = False

    # Gameplay / freemium
    # ТЗ v1.5, раздел 4.7: users.lives_current / lives_max = 10 по умолчанию. Лимит хранится
    # ещё и в колонке users.lives_max (миграция 0005) — чтобы менять его под акции без релиза.
    DEFAULT_LIVES_MAX: int = 10
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

    # Внешний адрес самого backend — нужен, чтобы собрать абсолютный confirmation_url для
    # платёжной заглушки (см. acquiring.py). На проде — публичный домен API.
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"
    # Куда заглушка ЮKassa возвращает браузер после «оплаты». На проде это делает реальный
    # эквайринг по return_url; здесь — страница фронтенда, которая опросит статус подписки.
    BILLING_RETURN_URL: str = "http://localhost:5173/profile"

    @property
    def cors_allow_origins(self) -> list[str]:
        raw = self.CORS_ALLOW_ORIGINS.strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _forbid_placeholder_secrets_outside_local(self) -> "Settings":
        """На развёрнутом окружении (не local/test/ci) дефолт-заглушка JWT_SECRET_KEY —
        открытая дверь: с ней кто угодно подделает токен и войдёт под любым пользователем."""
        if (
            self.ENVIRONMENT.lower() not in _LOCAL_ENVIRONMENTS
            and self.JWT_SECRET_KEY in _PLACEHOLDER_JWT_SECRETS
        ):
            raise ValueError(
                f"JWT_SECRET_KEY не задан (ENVIRONMENT={self.ENVIRONMENT}). "
                "Сгенерируйте секрет и пропишите в .env: "
                'python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
