import os

import redis


class RedisClient:
    """Use a shared Redis connection pool."""

    _pool = None

    @classmethod
    def _build_pool(cls):
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
        """Get a Redis client from the shared pool."""
        if cls._pool is None:
            cls._build_pool()
        return redis.StrictRedis(connection_pool=cls._pool)

