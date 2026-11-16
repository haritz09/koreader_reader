"""Shared runner for tests that need a real PostgreSQL session."""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import engine, session_factory


def run_against_postgres(
    work: Callable[[AsyncSession], Awaitable[None]],
) -> None:
    async def main() -> None:
        try:
            async with session_factory() as session:
                await work(session)
        finally:
            await engine.dispose()

    asyncio.run(main())
