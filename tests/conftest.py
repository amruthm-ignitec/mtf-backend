"""Pytest configuration and fixtures."""
import os

import pytest


@pytest.fixture(scope="session")
def require_db():
    """Skip tests that need a real database when DATABASE_URL is not set."""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set; skipping integration test")
