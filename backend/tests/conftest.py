import asyncio
import os
from collections.abc import Generator

import psycopg
import pytest

from core.config import settings

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _sync_database_url() -> str:
    return settings.database_url.replace("+psycopg", "")


@pytest.fixture(scope="session")
def postgres_connection() -> Generator[psycopg.Connection, None, None]:
    try:
        connection = psycopg.connect(_sync_database_url())
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL is not available: {error}")

    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def clean_postgres_database(postgres_connection: psycopg.Connection) -> None:
    postgres_connection.execute(
        "TRUNCATE TABLE chunks, chapters, books RESTART IDENTITY CASCADE"
    )
    postgres_connection.commit()
    yield
    postgres_connection.execute(
        "TRUNCATE TABLE chunks, chapters, books RESTART IDENTITY CASCADE"
    )
    postgres_connection.commit()


@pytest.fixture(scope="session")
def e2e_enabled() -> None:
    if os.getenv("RUN_E2E") != "1":
        pytest.skip("Set RUN_E2E=1 to run Docker Compose end-to-end tests")
