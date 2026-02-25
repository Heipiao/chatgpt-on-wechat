import os

try:
    import redis
    _redis_available = True
except ImportError:
    redis = None
    _redis_available = False


class RedisClient:
    """Use a shared Redis connection pool. 未安装 redis 包时 get_client() 返回 None，调用方需做 fallback。"""

    _pool = None

    @classmethod
    def is_available(cls) -> bool:
        return _redis_available

    @classmethod
    def _build_pool(cls):
        if not _redis_available:
            return
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD")
        db = int(os.getenv("REDIS_DB", "0"))
        max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

        cls._pool = redis.ConnectionPool(
            host=host,
            port=port,
            password=password,
            db=db,
            decode_responses=True,
            max_connections=max_connections,
        )

    @classmethod
    def get_client(cls):
        """Get a Redis client from the shared pool. 未安装 redis 时返回 None。"""
        if not _redis_available:
            return None
        if cls._pool is None:
            cls._build_pool()
        return redis.StrictRedis(connection_pool=cls._pool)

