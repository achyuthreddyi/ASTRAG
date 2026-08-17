"""Engine and request-scoped sessions.

One engine per process, built lazily so importing the package does not need a
reachable database.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from astrag.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine())


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Tests override this with a rolled-back session."""
    with get_sessionmaker()() as session:
        yield session
