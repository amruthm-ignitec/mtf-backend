"""Async database engine and session for PostgreSQL."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


def get_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url_async, echo=False)


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
