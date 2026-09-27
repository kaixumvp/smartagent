"""HTTP middleware: trace-id propagation and token-bucket rate limiting.

Auth/tenant are handled as dependencies (api/security.py), not middleware, because they must
return structured 401/403 responses and vary per-route. The middleware here only covers
concerns that apply uniformly: tracing every request and throttling by caller.
"""

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from smartagent.config import get_settings

# Lua token bucket: refill at `rate` tokens/sec up to `capacity`, consume one on success.
_TOKEN_BUCKET_LUA = """
local tokens = tonumber(redis.call('HMGET', KEYS[1], 'tokens')[1])
local last = tonumber(redis.call('HMGET', KEYS[1], 'ts')[1])
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
if tokens == nil then tokens = capacity end
if last == nil then last = now end
local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * rate)
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
  redis.call('EXPIRE', KEYS[1], 120)
  return 1
end
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], 120)
return 0
"""


class RateLimiter:
    """Redis-backed token bucket."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def allow(self, key: str, capacity: int, per_min: int) -> bool:
        rate = per_min / 60.0
        result = await self._redis.eval(_TOKEN_BUCKET_LUA, 1, key, capacity, rate, time.time())
        return bool(result)


async def trace_middleware(request: Request, call_next):
    """Assign a trace_id to each request and echo it back on the response."""
    trace_id = request.headers.get("X-Trace-Id") or f"trace_{uuid.uuid4().hex}"
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


async def rate_limit_middleware(request: Request, call_next):
    """Throttle requests per caller (JWT-derived key, falling back to client host)."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return await call_next(request)

    key = _rate_limit_key(request)
    limiter = RateLimiter(request.app.state.redis)
    allowed = await limiter.allow(key, settings.rate_limit_burst, settings.rate_limit_per_min)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "rate limit exceeded", "trace_id": request.state.trace_id}},
        )
    return await call_next(request)


def _rate_limit_key(request: Request) -> str:
    """Derive a stable key from the JWT sub/tenant, else the client host."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from smartagent.api.security import decode_token

            payload = decode_token(auth[7:])
            return f"rl:{payload.get('tenant_id', 'default')}:{payload.get('sub', 'anon')}"
        except Exception:  # noqa: BLE001 — fall through to host key
            pass
    return f"rl:{request.client.host if request.client else 'unknown'}"
