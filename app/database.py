"""Async database engine and session for PostgreSQL."""
import uuid
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# asyncpg does not support libpq params like sslmode; strip them and use connect_args for SSL
ASYNCPG_UNSUPPORTED_QUERY_KEYS = frozenset({"sslmode", "ssl_mode"})

def _async_engine_url_and_connect_args():
    settings = get_settings()
    raw = settings.database_url_async
    parsed = urlparse(raw)
    query = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = None
    for key in list(query.keys()):
        if key.lower() in ASYNCPG_UNSUPPORTED_QUERY_KEYS:
            vals = query.pop(key)
            if vals and sslmode is None:
                sslmode = vals[0]
    new_query = urlencode(query, doseq=True)
    url = urlunparse(parsed._replace(query=new_query))
    connect_args = {}
    if sslmode and str(sslmode).lower() in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = True
    return url, connect_args


def get_engine():
    url, connect_args = _async_engine_url_and_connect_args()
    kwargs = {"echo": False}
    if connect_args:
        kwargs["connect_args"] = connect_args
    return create_async_engine(url, **kwargs)


engine = get_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create tables if they do not exist. Import app.models before calling so tables are registered."""
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()
