"""访问令牌的 Redis 缓存。

缓存只是优化：Redis 不可用（连不上、超时、未部署）时一律降级为“直接去取新令牌”，
绝不让缓存设施的问题导致工具调用失败。
"""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from .config import settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "capability:token:"
# token 端点没返回 expires_in 时的兜底缓存时长
DEFAULT_TTL_SECONDS = 300
# 剩余有效期短于该值就不缓存，避免缓存一个马上就要失效的令牌
MIN_TTL_SECONDS = 10
# 提前这么多秒视为过期，给调用留出余量
SAFETY_MARGIN_SECONDS = 30
SOCKET_TIMEOUT_SECONDS = 2


def cache_key(fingerprint: dict[str, Any]) -> str:
    payload = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False, default=str)
    return KEY_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def secret_fingerprint(secrets: dict[str, Any]) -> str:
    """只把摘要放进缓存键，密钥明文不进 Redis 键名。"""
    payload = json.dumps(secrets, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_ttl(expires_in: Any) -> int | None:
    """返回缓存秒数；有效期太短则返回 None（不缓存）。"""
    if isinstance(expires_in, bool) or expires_in is None:
        return DEFAULT_TTL_SECONDS
    try:
        seconds = float(expires_in)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS
    if seconds <= 0:
        return DEFAULT_TTL_SECONDS
    ttl = int(seconds) - SAFETY_MARGIN_SECONDS
    return ttl if ttl >= MIN_TTL_SECONDS else None


def _client() -> redis.Redis:
    return redis.from_url(
        settings.redis_url,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
    )


async def get_token(key: str) -> str | None:
    if not settings.token_cache_enabled:
        return None
    try:
        async with _client() as client:
            value = await client.get(key)
    except (RedisError, OSError) as exc:
        logger.warning("Token 缓存不可用，跳过读取（%s）", type(exc).__name__)
        return None
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


async def store_token(key: str, token: str, expires_in: Any) -> None:
    if not settings.token_cache_enabled:
        return
    ttl = compute_ttl(expires_in)
    if ttl is None:
        return
    try:
        async with _client() as client:
            await client.set(key, token, ex=ttl)
    except (RedisError, OSError) as exc:
        logger.warning("Token 缓存不可用，跳过写入（%s）", type(exc).__name__)
