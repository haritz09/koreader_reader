import asyncio
import os
import time
from collections.abc import Generator

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from core.config import settings

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_OWNER_ID = "test-owner"


def _sync_database_url() -> str:
    return settings.database_url.replace("+psycopg", "")


TRUNCATE_ATTEMPTS = 5
TRUNCATE_RETRY_SECONDS = 0.2


def _truncate_all_tables(conn: psycopg.Connection) -> None:
    """Empty every table, retrying when the ARQ worker is still writing.
    """
    for attempt in range(TRUNCATE_ATTEMPTS):
        conn.rollback()
        rows = conn.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        ).fetchall()
        if not rows:
            conn.commit()
            return
        table_names = ", ".join(f"{row[0]}" for row in rows)
        try:
            conn.execute(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
        except psycopg.errors.DeadlockDetected:
            conn.rollback()
            if attempt == TRUNCATE_ATTEMPTS - 1:
                raise
            time.sleep(TRUNCATE_RETRY_SECONDS)
            continue
        conn.commit()
        return


def _seed_test_owner(conn: psycopg.Connection) -> None:
    """Every API request resolves to an owner, so the owner row must exist."""
    conn.execute(
        "INSERT INTO users (id, is_anonymous, created_at) "
        "VALUES (%s, true, now()) ON CONFLICT (id) DO NOTHING",
        (TEST_OWNER_ID,),
    )
    conn.commit()


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


@pytest.fixture(scope="session")
def run_migrations(postgres_connection: psycopg.Connection) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", _sync_database_url())
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def clean_postgres_database(run_migrations: None, postgres_connection: psycopg.Connection) -> None:
    _truncate_all_tables(postgres_connection)
    _seed_test_owner(postgres_connection)
    yield
    _truncate_all_tables(postgres_connection)


@pytest.fixture(autouse=True)
def default_owner() -> Generator[None, None, None]:
    """Authenticate every request as a fixed owner unless a test opts out.

    Tests that exercise the session contract clear this override to assert the
    401 path.
    """
    from api.dependencies import get_current_owner
    from main import app

    app.dependency_overrides[get_current_owner] = lambda: TEST_OWNER_ID
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_owner, None)


@pytest.fixture(scope="session")
def e2e_enabled() -> None:
    if os.getenv("RUN_E2E") != "1":
        pytest.skip("Set RUN_E2E=1 to run Docker Compose end-to-end tests")
