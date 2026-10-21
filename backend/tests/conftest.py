import asyncio
import os
import subprocess
from collections.abc import Generator, Iterator
from contextlib import contextmanager

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


WORKER_SERVICE = "worker"
REDIS_SERVICE = "redis"
COMPOSE_TIMEOUT_SECONDS = 120
WORKER_STOP_TIMEOUT_SECONDS = 1
TRUNCATE_LOCK_TIMEOUT = "10s"

_container_ids: dict[str, str] = {}


def _run(*command: str) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=COMPOSE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            " ".join(command) + " failed: " + result.stderr.strip()
        )
    return result.stdout.strip()


def _container_id(service: str) -> str:
    if service not in _container_ids:
        container_id = _run("docker", "compose", "ps", "-q", service)
        if not container_id:
            raise RuntimeError(f"the {service} container is not running")
        _container_ids[service] = container_id
    return _container_ids[service]


@contextmanager
def _worker_stopped() -> Iterator[None]:
    worker = _container_id(WORKER_SERVICE)
    redis = _container_id(REDIS_SERVICE)
    _run("docker", "stop", "-t", str(WORKER_STOP_TIMEOUT_SECONDS), worker)
    try:
        _run("docker", "exec", redis, "redis-cli", "FLUSHDB")
        yield
    finally:
        _run("docker", "start", worker)


@contextmanager
def _quiesced_database(enabled: bool) -> Generator[None, None, None]:
    if not enabled:
        yield
        return
    with _worker_stopped():
        yield


def _is_e2e(request: pytest.FixtureRequest) -> bool:
    return (
        os.getenv("RUN_E2E") == "1"
        and request.node.get_closest_marker("e2e") is not None
    )


def _truncate_all_tables(conn: psycopg.Connection) -> None:
    conn.rollback()
    conn.execute(f"SET lock_timeout = '{TRUNCATE_LOCK_TIMEOUT}'")
    rows = conn.execute(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
    ).fetchall()
    if rows:
        table_names = ", ".join(f"{row[0]}" for row in rows)
        conn.execute(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
    conn.commit()


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
def clean_postgres_database(
    request: pytest.FixtureRequest,
    run_migrations: None,
    postgres_connection: psycopg.Connection,
) -> Generator[None, None, None]:
    quiesce = _is_e2e(request)
    with _quiesced_database(quiesce):
        _truncate_all_tables(postgres_connection)
    _seed_test_owner(postgres_connection)
    yield
    with _quiesced_database(quiesce):
        _truncate_all_tables(postgres_connection)


@pytest.fixture(autouse=True)
def default_owner() -> Generator[None, None, None]:
    from api.dependencies import get_current_owner
    from main import app

    app.dependency_overrides[get_current_owner] = lambda: TEST_OWNER_ID
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_owner, None)


class _UnlimitedRateLimiter:
    async def acquire(self, key: str, limit: int, window_seconds: int):
        from core.ports.rate_limiter import RateLimitDecision

        return RateLimitDecision(allowed=True)


@pytest.fixture(autouse=True)
def allow_all_rate_limits() -> Generator[None, None, None]:
    from api.dependencies import get_rate_limiter
    from main import app

    app.dependency_overrides[get_rate_limiter] = lambda: _UnlimitedRateLimiter()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture(scope="session")
def e2e_enabled() -> None:
    if os.getenv("RUN_E2E") != "1":
        pytest.skip("Set RUN_E2E=1 to run Docker Compose end-to-end tests")
