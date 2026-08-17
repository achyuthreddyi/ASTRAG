"""Tests run against the docker-compose PostgreSQL, per the plan: pgvector,
JSONB and FTS do not exist in SQLite, so the parts most likely to break would
be the uncovered ones.

`docker compose up -d` must be running.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from astrag.settings import get_settings

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
