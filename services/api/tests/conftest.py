"""Pytest fixtures and configuration."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db import Base, get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.services.rate_limiter import clear_memory_store

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    """Clear in-memory rate limiting state before every test."""
    clear_memory_store()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite database session per test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient configured with dependency overrides for database session."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_test_users(db_session: AsyncSession) -> dict[str, Any]:
    """Seed sample users for testing auth flows."""
    student = User(
        id=uuid.uuid4(),
        email="student@campus.local",
        name="Active Student",
        role=UserRole.STUDENT,
        password_hash=hash_password("StudentPass123!"),
        is_active=True,
    )
    professor = User(
        id=uuid.uuid4(),
        email="prof@campus.local",
        name="Active Professor",
        role=UserRole.PROFESSOR,
        password_hash=hash_password("ProfPass123!"),
        is_active=True,
    )
    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@campus.local",
        name="Inactive Student",
        role=UserRole.STUDENT,
        password_hash=hash_password("InactivePass123!"),
        is_active=False,
    )

    db_session.add_all([student, professor, inactive_user])
    await db_session.commit()

    return {
        "student": student,
        "professor": professor,
        "inactive": inactive_user,
        "student_password": "StudentPass123!",
        "professor_password": "ProfPass123!",
        "inactive_password": "InactivePass123!",
    }
