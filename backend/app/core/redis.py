import redis
from app.core.config import settings
import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

def _candidate_urls(base_url: str):
    candidates = [base_url]
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port
        if host in {"localhost", "127.0.0.1"} and port == 6379:
            netloc = f"{host}:6380"
            if parsed.username and parsed.password:
                netloc = f"{parsed.username}:{parsed.password}@{host}:6380"
            elif parsed.username:
                netloc = f"{parsed.username}@{host}:6380"
            candidates.append(urlunparse(parsed._replace(netloc=netloc)))
    except Exception:
        pass
    return candidates


redis_client = None
last_error = None
for redis_url in _candidate_urls(settings.REDIS_URL):
    try:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            # Fail fast when Redis is down (common in dev/VPS without Redis).
            # Slow connect timeouts will block API responses that use caching.
            socket_connect_timeout=0.2,
            socket_timeout=0.5,
            retry_on_timeout=False,
        )
        client.ping()
        redis_client = client
        logger.info(f"Redis connected successfully: {redis_url}")
        break
    except Exception as e:
        last_error = e

if redis_client is None:
    logger.error(f"Redis connection failed: {last_error}")
