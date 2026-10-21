from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class RateLimiter(Protocol):
    async def acquire(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        ...
