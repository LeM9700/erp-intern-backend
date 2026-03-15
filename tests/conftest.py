"""
Shared fixtures for unit & integration tests.

Uses an in-memory SQLite database (async) so tests run without Postgres.
PostgreSQL-specific UUID type is monkey-patched to work with SQLite.
"""
import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

# ---------------------------------------------------------------------------
# Monkey-patch SQLAlchemy Uuid bind_processor to accept string UUIDs
# (SQLite doesn't have native UUID, and the Uuid type's bind_processor
#  calls value.hex which fails on strings passed from JWT sub claims)
# ---------------------------------------------------------------------------
from sqlalchemy.sql import sqltypes as _sqltypes

_orig_uuid_bind = _sqltypes.Uuid.bind_processor


def _patched_uuid_bind(self, dialect):
    processor = _orig_uuid_bind(self, dialect)
    if processor is not None:
        def safe_process(value):
            if value is not None:
                if isinstance(value, str):
                    try:
                        value = uuid.UUID(value)
                    except ValueError:
                        pass
                return processor(value)
            return None
        return safe_process
    return processor


_sqltypes.Uuid.bind_processor = _patched_uuid_bind

# ---------------------------------------------------------------------------
# Override settings BEFORE any app import so the whole app uses test config
# ---------------------------------------------------------------------------
import os

os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["S3_ENDPOINT_URL"] = "http://localhost:9000"
os.environ["S3_ACCESS_KEY"] = "minioadmin"
os.environ["S3_SECRET_KEY"] = "minioadmin"
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["S3_REGION"] = "us-east-1"
os.environ["S3_PRESIGN_EXPIRATION"] = "3600"

# ---------------------------------------------------------------------------
# Now import app modules
# ---------------------------------------------------------------------------
from app.db.base import Base
from app.models.user import User, UserRole
from app.models.attendance import AttendanceSession  # noqa: F401
from app.models.task import Task, TaskProof, TaskReview, TaskComment  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.core.security import hash_password, create_access_token
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Patch seed_admin to avoid DB calls during lifespan
# ---------------------------------------------------------------------------
import app.main as main_module


async def _noop_seed_admin():
    """No-op seed during tests."""
    pass


main_module.seed_admin = _noop_seed_admin

from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Async SQLite engine for tests
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

TestSessionFactory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Create / drop tables for each test function
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Recreate all tables before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# DB session fixture
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session


# ---------------------------------------------------------------------------
# Override FastAPI's get_db dependency
# ---------------------------------------------------------------------------
async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Async HTTP client (uses ASGI transport – no real server needed)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Pre-built users
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        hashed_password=hash_password("Admin123!"),
        full_name="Admin Test",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def intern_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="intern@test.com",
        hashed_password=hash_password("Intern123!"),
        full_name="Intern Test",
        role=UserRole.INTERN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def intern_user2(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="intern2@test.com",
        hashed_password=hash_password("Intern123!"),
        full_name="Intern2 Test",
        role=UserRole.INTERN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    return create_access_token(str(admin_user.id), {"role": admin_user.role.value})


@pytest_asyncio.fixture
async def intern_token(intern_user: User) -> str:
    return create_access_token(str(intern_user.id), {"role": intern_user.role.value})


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def intern_headers(intern_token: str) -> dict:
    return {"Authorization": f"Bearer {intern_token}"}


# ---------------------------------------------------------------------------
# Helper: create a confirmed file record in DB (no real S3)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def confirmed_file(db_session: AsyncSession, intern_user: User) -> File:
    f = File(
        id=uuid.uuid4(),
        original_filename="photo.jpg",
        stored_path=f"uploads/attendance/{intern_user.id}/photo.jpg",
        mime_type="image/jpeg",
        confirmed=True,
        uploaded_by=intern_user.id,
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


@pytest_asyncio.fixture
async def confirmed_file2(db_session: AsyncSession, intern_user: User) -> File:
    f = File(
        id=uuid.uuid4(),
        original_filename="photo2.jpg",
        stored_path=f"uploads/attendance/{intern_user.id}/photo2.jpg",
        mime_type="image/jpeg",
        confirmed=True,
        uploaded_by=intern_user.id,
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f
