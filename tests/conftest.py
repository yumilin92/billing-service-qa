"""
Shared pytest fixtures for the unit + API tests.

conftest.py is special: pytest loads it automatically and any fixture defined
here is available to every test file below this folder — no imports needed.

The big idea in this file is TEST ISOLATION: every test gets its own brand-new,
empty, in-memory database. Tests never see each other's data and never touch
your real billing.db. That's what makes a suite trustworthy — a test passes or
fails because of the code, not because of leftover data from another test.
"""
import os

# Point the app at an in-memory DB *before* importing it, so importing app.main
# (which creates tables on import) never creates a stray file on disk.
os.environ.setdefault("BILLING_DB_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite database, unique to each test.

    `sqlite://` (no path) = a database that lives only in RAM.
    `StaticPool` keeps ONE shared connection, so the schema we create is the
    same one the test sees (otherwise in-memory SQLite would give each
    connection its own empty DB).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)  # build the tables
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()  # throw the whole database away after the test


@pytest.fixture()
def client(db_session):
    """A TestClient whose requests use the per-test database above.

    We do this with FastAPI's `dependency_overrides`: wherever the app asks for
    `get_db`, give it our test session instead. This is the cleanest way to
    swap real infrastructure for test infrastructure.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()  # tidy up so tests stay independent
