import json
import os

from src.model import DeclarativeBaseModel

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DATABASE = os.getenv("DB_DATABASE")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

postgresql_url = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"
)
engine = create_engine(postgresql_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    DeclarativeBaseModel.metadata.create_all(engine)


class RedisClient:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
        )
        self.redis_client.ping()

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
        return self.redis_client.keys(pattern)
