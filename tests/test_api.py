"""Minimal API tests. Require DATABASE_URL (Postgres) for lifespan/DB."""
import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set; API tests need a running Postgres",
)

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_get_donor_404():
    """GET /donors/{id} returns 404 for unknown id (no DB needed with override)."""
    from app.database import async_session_factory
    from app.main import get_db

    async def override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/donors/{uuid4()}")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_document_status_404():
    """GET /documents/{id}/status returns 404 for unknown id."""
    from app.database import async_session_factory
    from app.main import get_db

    async def override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/documents/{uuid4()}/status")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
