import os

# Тесты работают с отдельной БД tasks_test. URL задаётся до импорта приложения,
# чтобы app.config не требовал DATABASE_URL и не смотрел в рабочую БД.
TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/tasks_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from collections.abc import AsyncIterator  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import make_url, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app import models  # noqa: E402,F401  регистрирует модели в Base.metadata
from app.db import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402


async def ensure_database(url: str) -> None:
    """Создаёт тестовую БД, если её нет (локально и в docker compose)."""
    u = make_url(url)
    conn = await asyncpg.connect(
        user=u.username,
        password=u.password,
        host=u.host,
        port=u.port or 5432,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", u.database
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{u.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await ensure_database(TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # Каждый тест начинается на чистых таблицах, счётчики id сбрасываются
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE tasks, users RESTART IDENTITY CASCADE"))
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def user(client: AsyncClient) -> dict:
    resp = await client.post(
        "/users", json={"email": "alice@example.com", "name": "Alice"}
    )
    assert resp.status_code == 201
    return resp.json()
