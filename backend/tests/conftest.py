import asyncio
import os
from collections.abc import Generator

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from core.config import settings

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _sync_database_url() -> str:
    return settings.database_url.replace("+psycopg", "")


def _truncate_all_tables(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    if rows:
        table_names = ", ".join(f"{row[0]}" for row in rows)
        conn.execute(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
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
    yield
    _truncate_all_tables(postgres_connection)


@pytest.fixture(scope="session")
def e2e_enabled() -> None:
    if os.getenv("RUN_E2E") != "1":
        pytest.skip("Set RUN_E2E=1 to run Docker Compose end-to-end tests")
