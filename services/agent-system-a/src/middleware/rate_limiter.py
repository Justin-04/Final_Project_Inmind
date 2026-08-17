"""
Per-User Rate Limiter — Sliding Window via Redis.

Uses Redis INCR + EXPIRE for a simple fixed-window rate limit per user.
If Redis is unavailable, rate limiting is skipped (fail-open).

Config via environment variables:
- RATE_LIMIT_REQUESTS: max requests per window (default: 20)
- RATE_LIMIT_WINDOW: window size in seconds (default: 60)
"""

import os
import logging

from fastapi import HTTPException, Request, Depends

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
RATE_LIMIT_PREFIX = "rate_limit:"

_redis = None


def _get_redis():
    """Lazy Redis connection for rate limiting."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
        _redis.ping()
        logger.info(f"Rate limiter: Redis connected (limit={RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s)")
        return _redis
    except Exception as e:
        logger.warning(f"Rate limiter: Redis unavailable ({e}) — rate limiting disabled")
        return None


class RateLimiter:
    """Per-user rate limiter using Redis fixed-window counter."""

    def __init__(self, max_requests: int = None, window_seconds: int = None):
        self.max_requests = max_requests or RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or RATE_LIMIT_WINDOW
        self.redis = _get_redis()

    def check(self, user_id: str) -> dict:
        """
        Check if user is within rate limit.

        Returns:
            {"allowed": bool, "remaining": int, "limit": int, "reset_in": int}
        """
        if self.redis is None:
            # Fail-open: if Redis is down, don't block users
            return {"allowed": True, "remaining": self.max_requests, "limit": self.max_requests, "reset_in": 0}

        key = f"{RATE_LIMIT_PREFIX}{user_id}"

        try:
            # Increment counter
            current = self.redis.incr(key)

            # Set expiry on first request in window
            if current == 1:
                self.redis.expire(key, self.window_seconds)

            # Get TTL for reset info
            ttl = self.redis.ttl(key)
            remaining = max(0, self.max_requests - current)

            if current > self.max_requests:
                return {
                    "allowed": False,
                    "remaining": 0,
                    "limit": self.max_requests,
                    "reset_in": ttl if ttl > 0 else self.window_seconds,
                }

            return {
                "allowed": True,
                "remaining": remaining,
                "limit": self.max_requests,
                "reset_in": ttl if ttl > 0 else self.window_seconds,
            }

        except Exception as e:
            logger.warning(f"Rate limiter error: {e} — allowing request")
            return {"allowed": True, "remaining": self.max_requests, "limit": self.max_requests, "reset_in": 0}


# Singleton instance
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def check_rate_limit(request: Request):
    """
    FastAPI dependency that enforces rate limiting.
    Must be used AFTER get_current_user (needs user_id from JWT).

    Usage in endpoint:
        @app.post("/api/v1/chat")
        async def chat(request: ChatRequest, user: dict = Depends(get_current_user), _=Depends(check_rate_limit)):
    """
    # Extract user_id from the request state (set by auth middleware)
    # Fallback to IP if user not authenticated
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        user_id = user.get("sub", user.get("user_id", "anonymous"))
    else:
        user_id = request.client.host if request.client else "unknown"

    limiter = get_rate_limiter()
    result = limiter.check(user_id)

    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Maximum {result['limit']} requests per {RATE_LIMIT_WINDOW} seconds. Try again in {result['reset_in']}s.",
                "retry_after": result["reset_in"],
            },
            headers={"Retry-After": str(result["reset_in"])},
        )
