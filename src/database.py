from contextlib import contextmanager
from contextvars import ContextVar
import json
import os

from src.cfg.database import SessionLocal

import redis
from sqlalchemy.orm import Session

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

db_session_ctx: ContextVar[Session] = ContextVar("db_session_ctx")


def get_db_session():
    return db_session_ctx.get()


@contextmanager
def db_session_manager():
    session = SessionLocal()
    token = db_session_ctx.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        db_session_ctx.reset(token)


class RedisClient:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
        )

    def set(self, key, value, expiration=3600):
        self.redis_client.setex(key, expiration, json.dumps(value))

    def get(self, key, default):
        value = self.redis_client.get(key)
        if value is None:
            return default
        return json.loads(value)

    def delete(self, *keys):
        return self.redis_client.delete(*keys)

    def list_keys(self, pattern="*"):
        _, keys = self.redis_client.scan(match=pattern)
        return keys

    def get_many(self, pattern="*"):
        keys = self.list_keys(pattern)
        return self.redis_client.mget(keys)

    def get_ttl(self, pattern="*"):
        keys = self.list_keys(pattern)
        return [self.redis_client.ttl(key) for key in keys]

    def get_many_with_ttl(self, pattern="*"):
        keys = self.list_keys(pattern)
        values = self.redis_client.mget(keys)
        keys_ttl = [self.redis_client.ttl(key) for key in keys]

        return values, keys_ttl

    def acquire_lock(self, key, timeout=30):
        return self.redis_client.set(key, 1, nx=True, ex=timeout)

    def release_lock(self, key):
        return self.redis_client.delete(key)

    def close(self):
        self.redis_client.close()


redis_client = RedisClient()
