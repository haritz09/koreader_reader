"""Redis-backed fixed-window rate limiter."""

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.ports.rate_limiter import RateLimitDecision

logger = logging.getLogger(__name__)

# One round trip: increment, start the window on the first hit (or repair a key
# that lost its TTL), and return the remaining time for Retry-After.
_ACQUIRE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url)
        self._acquire = self._redis.register_script(_ACQUIRE_SCRIPT)

    async def acquire(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        try:
            count, ttl = await self._acquire(
                keys=[key],
                args=[window_seconds],
            )
        except RedisError:
            # Session creation must not fail because the limiter is down.
            logger.warning("Rate limiter unavailable; allowing the request", exc_info=True)
            return RateLimitDecision(allowed=True)

        if int(count) > limit:
            return RateLimitDecision(
                allowed=False,
                retry_after=max(int(ttl), 1),
            )
        return RateLimitDecision(allowed=True)

    async def aclose(self) -> None:
        await self._redis.aclose()
