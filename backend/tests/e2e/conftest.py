import os
import time
from collections.abc import Callable, Generator

import httpx
import pytest


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture
def e2e_client(
    e2e_base_url: str, clean_postgres_database
) -> Generator[httpx.Client, None, None]:
    """A client with a real anonymous session cookie.

    The database is truncated first, so the session created here belongs to a
    fresh owner and every request after it carries the httpOnly cookie.
    """
    with httpx.Client(base_url=e2e_base_url, timeout=10.0) as client:
        session_response = client.post("/api/v1/session")
        assert session_response.status_code == 201, session_response.text
        yield client


@pytest.fixture
def wait_for_ready(e2e_client: httpx.Client) -> Callable[..., dict]:
    def wait(book_id: str, timeout: float = 30) -> dict:
        deadline = time.monotonic() + timeout
        status = None
        while time.monotonic() < deadline:
            response = e2e_client.get(f"/api/v1/ebooks/{book_id}")
            assert response.status_code == 200
            status = response.json()
            if status["processing_status"] in {"ready", "failed"}:
                return status
            time.sleep(0.25)
        raise AssertionError(f"book never finished processing: {status}")

    return wait
