from collections.abc import AsyncIterator, Generator

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_book_repository
from db.repositories.postgres_book_repository import PostgresBookRepository
from db.session import session_factory
from main import app


async def _real_book_repository() -> AsyncIterator[PostgresBookRepository]:
    async with session_factory() as session:
        yield PostgresBookRepository(session)


@pytest.fixture
def postgres_app_client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_book_repository] = _real_book_repository
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
