import os
from collections.abc import Generator

import httpx
import pytest


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture
def e2e_client(e2e_base_url: str) -> Generator[httpx.Client, None, None]:
    with httpx.Client(base_url=e2e_base_url, timeout=10.0) as client:
        yield client
