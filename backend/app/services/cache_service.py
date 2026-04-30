import json
import time
from typing import Any, Optional
from app.core.redis import redis_client
import logging

logger = logging.getLogger(__name__)
_local_cache: dict[str, tuple[float, str]] = {}
_redis_unavailable = False
_redis_retry_after = 0.0
_LOCAL_CACHE_MAX_KEYS = 5000


class CacheService:
    """Centralized Redis caching service"""

    # Cache TTLs (in seconds)
    TTL_SHORT = 300      # 5 minutes
    TTL_MEDIUM = 900     # 15 minutes
    TTL_LONG = 1800      # 30 minutes
    TTL_VERY_LONG = 3600  # 1 hour

    @staticmethod
    def _get_local_value(key: str) -> Optional[Any]:
        cached = _local_cache.get(key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at < time.time():
            _local_cache.pop(key, None)
            return None
        try:
            return json.loads(payload)
        except Exception:
            _local_cache.pop(key, None)
            return None

    @staticmethod
    def _set_local_value(key: str, value: Any, ttl: int) -> bool:
        try:
            # Keep fallback cache bounded in long-running processes.
            if len(_local_cache) >= _LOCAL_CACHE_MAX_KEYS:
                now = time.time()
                expired = [k for k, (exp, _) in _local_cache.items() if exp < now]
                for k in expired:
                    _local_cache.pop(k, None)
                if len(_local_cache) >= _LOCAL_CACHE_MAX_KEYS:
                    for k in list(_local_cache.keys())[: max(1, len(_local_cache) // 10)]:
                        _local_cache.pop(k, None)
            _local_cache[key] = (time.time() + max(1, int(ttl)), json.dumps(value, default=str))
            return True
        except Exception:
            return False

    @staticmethod
    def _should_try_redis() -> bool:
        global _redis_unavailable
        global _redis_retry_after
        if not redis_client:
            return False
        if not _redis_unavailable:
            return True
        if time.time() < _redis_retry_after:
            return False
        try:
            redis_client.ping()
            _redis_unavailable = False
            return True
        except Exception:
            _redis_retry_after = time.time() + 60
            return False

    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        global _redis_unavailable
        global _redis_retry_after
        if not CacheService._should_try_redis():
            return CacheService._get_local_value(key)
        try:
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            _redis_unavailable = True
            _redis_retry_after = time.time() + 60
            return CacheService._get_local_value(key)
        return None

    @staticmethod
    def set(key: str, value: Any, ttl: int = TTL_MEDIUM) -> bool:
        """Set value in Redis cache with TTL"""
        global _redis_unavailable
        global _redis_retry_after
        if not CacheService._should_try_redis():
            return CacheService._set_local_value(key, value, ttl)
        try:
            redis_client.setex(key, ttl, json.dumps(value, default=str))
            return True
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            _redis_unavailable = True
            _redis_retry_after = time.time() + 60
            return CacheService._set_local_value(key, value, ttl)

    @staticmethod
    def delete(key: str) -> bool:
        """Delete key from Redis cache"""
        global _redis_unavailable
        if not redis_client or _redis_unavailable:
            _local_cache.pop(key, None)
            return True
        try:
            redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            _redis_unavailable = True
            _local_cache.pop(key, None)
            return True

    @staticmethod
    def delete_pattern(pattern: str) -> bool:
        """Delete all keys matching pattern"""
        global _redis_unavailable
        if not redis_client or _redis_unavailable:
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                for key in list(_local_cache.keys()):
                    if key.startswith(prefix):
                        _local_cache.pop(key, None)
                return True
            _local_cache.pop(pattern, None)
            return True
        try:
            keys = list(redis_client.scan_iter(match=pattern, count=500))
            if keys:
                redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Redis delete pattern error for {pattern}: {e}")
            _redis_unavailable = True
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                for key in list(_local_cache.keys()):
                    if key.startswith(prefix):
                        _local_cache.pop(key, None)
                return True
            _local_cache.pop(pattern, None)
            return True

    # Specific cache operations

    @staticmethod
    def get_report_cache(report_type: str, params: dict) -> Optional[Any]:
        """Get cached report data"""
        params_str = "_".join(f"{k}:{v}" for k, v in sorted(params.items()))
        key = f"report:{report_type}:{params_str}"
        return CacheService.get(key)

    @staticmethod
    def set_report_cache(report_type: str, params: dict, value: Any, ttl: int = TTL_MEDIUM) -> bool:
        """Cache report data"""
        params_str = "_".join(f"{k}:{v}" for k, v in sorted(params.items()))
        key = f"report:{report_type}:{params_str}"
        return CacheService.set(key, value, ttl)

    @staticmethod
    def invalidate_report_cache(report_type: str):
        """Invalidate all cached reports of a specific type"""
        pattern = f"report:{report_type}:*"
        return CacheService.delete_pattern(pattern)

    @staticmethod
    def get_inventory_cache(inventory_id: Optional[int] = None) -> Optional[Any]:
        """Get cached inventory data"""
        if inventory_id:
            key = f"inventory:{inventory_id}"
        else:
            key = "inventory:list"
        return CacheService.get(key)

    @staticmethod
    def set_inventory_cache(value: Any, inventory_id: Optional[int] = None, ttl: int = TTL_SHORT) -> bool:
        """Cache inventory data"""
        if inventory_id:
            key = f"inventory:{inventory_id}"
        else:
            key = "inventory:list"
        return CacheService.set(key, value, ttl)

    @staticmethod
    def invalidate_inventory_cache():
        """Invalidate all inventory caches"""
        return CacheService.delete_pattern("inventory:*")

    @staticmethod
    def get_garment_cache(garment_id: Optional[int] = None) -> Optional[Any]:
        """Get cached garment data"""
        if garment_id:
            key = f"garment:{garment_id}"
        else:
            key = "garment:list"
        return CacheService.get(key)

    @staticmethod
    def set_garment_cache(value: Any, garment_id: Optional[int] = None, ttl: int = TTL_LONG) -> bool:
        """Cache garment data"""
        if garment_id:
            key = f"garment:{garment_id}"
        else:
            key = "garment:list"
        return CacheService.set(key, value, ttl)

    @staticmethod
    def invalidate_garment_cache():
        """Invalidate all garment caches"""
        return CacheService.delete_pattern("garment:*")

    # Integration cache operations

    @staticmethod
    def invalidate_today_cache():
        """Invalidate today's sales caches (use after data changes)."""
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        today = datetime.now(IST).strftime('%Y-%m-%d')
        CacheService.delete_pattern(f"uc:today:{today}")
        CacheService.delete_pattern("uc:channels:today:*")

    @staticmethod
    def invalidate_monthly_cache(year: int = None, month: int = None):
        """Invalidate monthly report caches."""
        if year is not None and month is not None:
            CacheService.delete_pattern(f"uc:best_skus:{year}:{month}:*")
            CacheService.delete_pattern(f"uc:cod_prepaid:{year}:{month}")
        else:
            CacheService.delete_pattern("uc:best_skus:*")
            CacheService.delete_pattern("uc:cod_prepaid:*")

    @staticmethod
    def invalidate_all_uc_cache():
        """Invalidate all Unicommerce integration caches."""
        return CacheService.delete_pattern("uc:*")

    # Raw materials cache operations

    @staticmethod
    def get_fabric_cache(fabric_id: Optional[int] = None) -> Optional[Any]:
        """Get cached fabric data"""
        if fabric_id:
            key = f"fabric:{fabric_id}"
        else:
            key = "fabric:list"
        return CacheService.get(key)

    @staticmethod
    def set_fabric_cache(value: Any, fabric_id: Optional[int] = None, ttl: int = TTL_LONG) -> bool:
        """Cache fabric data"""
        if fabric_id:
            key = f"fabric:{fabric_id}"
        else:
            key = "fabric:list"
        return CacheService.set(key, value, ttl)

    @staticmethod
    def invalidate_fabric_cache():
        """Invalidate all fabric caches"""
        return CacheService.delete_pattern("fabric:*")

    @staticmethod
    def get_yarn_cache(yarn_id: Optional[int] = None) -> Optional[Any]:
        """Get cached yarn data"""
        if yarn_id:
            key = f"yarn:{yarn_id}"
        else:
            key = "yarn:list"
        return CacheService.get(key)

    @staticmethod
    def set_yarn_cache(value: Any, yarn_id: Optional[int] = None, ttl: int = TTL_LONG) -> bool:
        """Cache yarn data"""
        if yarn_id:
            key = f"yarn:{yarn_id}"
        else:
            key = "yarn:list"
        return CacheService.set(key, value, ttl)

    @staticmethod
    def invalidate_yarn_cache():
        """Invalidate all yarn caches"""
        return CacheService.delete_pattern("yarn:*")

    # Financial cache operations

    @staticmethod
    def invalidate_ads_cache():
        """Invalidate all ads caches"""
        return CacheService.delete_pattern("ads:*")

    @staticmethod
    def invalidate_discounts_cache():
        """Invalidate all discounts caches"""
        return CacheService.delete_pattern("discounts:*")

    @staticmethod
    def invalidate_sales_cache():
        """Invalidate all sales caches"""
        return CacheService.delete_pattern("sales:*")

    # Production cache operations

    @staticmethod
    def invalidate_production_cache():
        """Invalidate all production plan caches"""
        return CacheService.delete_pattern("production:*")
