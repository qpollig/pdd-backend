"""Тестовая инфраструктура.

Ключевые решения:
  * ОТДЕЛЬНАЯ БД `<dev_db>_test` на том же Postgres, что и dev (docker-compose db-сервис).
    Дев-БД с реальными пользователями тесты не трогают — приложение ходит в БД только через
    зависимость get_db, которая здесь подменяется на сессию тестовой БД.
  * Схема создаётся ОДИН раз за сессию (Base.metadata.create_all), не пересоздаётся на тест.
  * Изоляция тестов — внешняя транзакция + SAVEPOINT (join_transaction_mode="create_savepoint"):
    всё, что тест и код под тестом записали (включая commit внутри get_db), откатывается после
    теста. Поэтому повторный прогон без ручной очистки тоже зелёный.
  * In-memory rate limiter чистится между тестами (autouse-фикстура).
"""

import asyncio
import os
import re
import sys

# ── ENV до импорта app: тестовое окружение, mock-OAuth, SMTP-заглушка ─────────────────────────
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OAUTH_ALLOW_MOCK", "true")
os.environ["YANDEX_CLIENT_ID"] = ""
os.environ["YANDEX_CLIENT_SECRET"] = ""
os.environ["VK_CLIENT_ID"] = ""
os.environ["VK_CLIENT_SECRET"] = ""
os.environ["SMTP_HOST"] = ""  # -> ConsoleEmailSender
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use")

if sys.platform == "win32":
    # asyncpg + Windows: ProactorEventLoop иногда капризничает, Selector надёжнее.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 — регистрирует все таблицы в Base.metadata
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.auth_identity import AuthIdentity, AuthIdentityType, PasswordResetToken
from app.models.user import User
from app.services import rate_limit
from app.services.passwords import hash_password

# ── URL тестовой БД ──────────────────────────────────────────────────────────────────────────
_DEV_URL = make_url(str(settings.DATABASE_URL))
TEST_DB_NAME = os.environ.get("TEST_DATABASE_NAME") or f"{_DEV_URL.database}_test"
TEST_DB_URL = _DEV_URL.set(database=TEST_DB_NAME)
_ADMIN_URL = _DEV_URL.set(database="postgres")  # для CREATE/DROP DATABASE

# Предохранители: не дать тестам случайно работать с дев-БД.
assert TEST_DB_NAME != _DEV_URL.database, "TEST_DB_NAME совпал с дев-БД"
assert "test" in TEST_DB_NAME, f"имя тестовой БД должно содержать 'test', получено {TEST_DB_NAME!r}"


async def _recreate_test_database() -> None:
    admin = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await admin.dispose()

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _drop_test_database() -> None:
    admin = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def _test_schema():
    """Один раз за сессию: пересоздать тестовую БД и накатить схему. Синхронная фикстура с
    собственным asyncio.run() — не завязана на loop-скоуп pytest-asyncio.
    НЕ autouse: подтягивается только через db_session, поэтому чисто-юнитовые тесты
    (test_passwords / test_rate_limit / test_email) идут вообще без Postgres."""
    asyncio.run(_recreate_test_database())
    yield
    asyncio.run(_drop_test_database())


@pytest_asyncio.fixture
async def db_session(_test_schema):
    """Сессия к тестовой БД внутри внешней транзакции. Всё записанное за тест (в т.ч. commit
    внутри get_db) откатывается в finally — тесты идемпотентны, мусор не копится."""
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest_asyncio.fixture
async def client(db_session):
    """httpx.AsyncClient поверх ASGI-приложения. get_db подменён на тестовую сессию, поэтому
    все запросы идут в тестовую БД и в одну транзакцию с тестом."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mail_outbox(monkeypatch):
    """Перехватывает письма из auth-эндпоинтов (get_email_sender вызывается там напрямую,
    это не Depends). Возвращает список EmailMessage."""
    outbox: list = []

    class _CapturingSender:
        async def send(self, message):
            outbox.append(message)

    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.get_email_sender", lambda: _CapturingSender()
    )
    return outbox


# ── Билдеры ──────────────────────────────────────────────────────────────────────────────────
DEFAULT_PASSWORD = "Sup3r-Secret-Pass"


@pytest_asyncio.fixture
async def make_user(db_session):
    """Фабрика «чистого» пользователя (без auth_identities)."""
    created: list[User] = []

    async def _make(*, name: str = "Test User", email: str | None = None) -> User:
        user = User(name=name, email=email)
        db_session.add(user)
        await db_session.flush()
        created.append(user)
        return user

    return _make


@pytest_asyncio.fixture
async def make_password_user(db_session):
    """Фабрика пользователя с password-identity и известным паролем.
    Возвращает (user, email, password)."""
    counter = {"n": 0}

    async def _make(
        *, email: str | None = None, password: str = DEFAULT_PASSWORD, name: str = "PW User"
    ) -> tuple[User, str, str]:
        counter["n"] += 1
        email = (email or f"pwuser{counter['n']}@example.com").lower()
        user = User(name=name, email=email)
        db_session.add(user)
        await db_session.flush()
        identity = AuthIdentity(
            user_id=user.id,
            type=AuthIdentityType.password,
            identifier=email,
            password_hash=hash_password(password),
        )
        db_session.add(identity)
        await db_session.flush()
        return user, email, password

    return _make


@pytest_asyncio.fixture
async def password_user(make_password_user):
    """Готовый пользователь с паролем — для тестов, которым нужен ровно один."""
    return await make_password_user()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_from_email_body(body_text: str) -> str:
    m = re.search(r"token=([A-Za-z0-9_\-]+)", body_text)
    assert m, f"в теле письма нет ?token=...:\n{body_text}"
    return m.group(1)


# экспортируем для тестов
__all__ = [
    "AuthIdentity",
    "AuthIdentityType",
    "PasswordResetToken",
    "User",
    "auth_header",
    "token_from_email_body",
    "select",
    "DEFAULT_PASSWORD",
]
