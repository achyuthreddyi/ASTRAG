"""Tests run against the docker-compose PostgreSQL, per the plan: pgvector,
JSONB and FTS do not exist in SQLite, so the parts most likely to break would
be the uncovered ones.

`docker compose up -d` must be running.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from astrag.api.app import app
from astrag.settings import get_settings
from astrag.storage.artifacts import LocalArtifactStore, get_artifact_store
from astrag.storage.database import get_db

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def engine():
    # Migrate rather than create_all, so the tests exercise the real DDL path.
    config = Config(REPO_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(get_settings().database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A session in a transaction that is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        yield session
    transaction.rollback()
    connection.close()


@pytest.fixture
def store(tmp_path):
    return LocalArtifactStore(tmp_path)


@pytest.fixture
def client(db, store):
    """API client sharing the test transaction, so endpoint commits still roll back."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_artifact_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
