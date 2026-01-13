"""Pytest configuration and fixtures."""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires running services)"
    )
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Set test environment before importing app
os.environ["DATABASE_URL"] = "postgresql+asyncpg://evidence:evidence_secret@localhost:5432/evidence_repository_test"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["FILE_STORAGE_ROOT"] = "./data/test_files"
os.environ["API_KEYS"] = "test-api-key"
os.environ["DEBUG"] = "true"

from evidence_repository.db.session import get_db_session
from evidence_repository.main import app
from evidence_repository.models.base import Base
from evidence_repository.storage import LocalFilesystemStorage


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session.

    Each test gets a fresh session with transactions rolled back.
    """
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client.

    Overrides the database dependency to use test session.
    """

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-api-key"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def storage() -> LocalFilesystemStorage:
    """Create test storage backend."""
    return LocalFilesystemStorage(base_path="./data/test_files")


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Sample PDF content for testing."""
    # Minimal valid PDF
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 24 Tf 100 700 Td (Test PDF) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
300
%%EOF"""


@pytest.fixture
def sample_text_content() -> bytes:
    """Sample text content for testing."""
    return b"""This is a sample legal document for testing.

Section 1: Introduction
This document contains important legal information.

Section 2: Terms and Conditions
The following terms apply to all parties involved.

Section 3: Conclusion
In conclusion, this document serves as evidence."""


@pytest.fixture
def api_headers() -> dict:
    """Default API headers for testing."""
    return {
        "X-API-Key": "test-api-key",
        "Content-Type": "application/json",
    }
