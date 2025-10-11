"""Database setup utilities for the Teller sample app."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

LOGGER = logging.getLogger(__name__)


def build_database_url() -> str:
    """Return the database URL, defaulting to a local SQLite database.

    The Render deployment provides ``DATABASE_INTERNAL_URL``. When running
    locally we fall back to ``sqlite:///teller.db`` so developers do not need a
    Postgres instance.
    """

    url = os.getenv("DATABASE_INTERNAL_URL")
    if url:
        # Convert postgresql:// to postgresql+psycopg:// for psycopg3
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]

        # Render also supplies DATABASE_SSLMODE which we surface as a query
        # parameter when present.
        sslmode = os.getenv("DATABASE_SSLMODE")
        if sslmode:
            connector = "?" if "?" not in url else "&"
            url = f"{url}{connector}sslmode={sslmode}"
        return url

    return os.getenv("DATABASE_URL", "sqlite:///teller.db")


def create_db_engine(echo: bool = False) -> Engine:
    """Create the SQLAlchemy engine."""

    url = build_database_url()
    # Mask password in log for security
    log_url = url
    if "@" in url and "://" in url:
        try:
            parts = url.split("://", 1)
            scheme = parts[0]
            rest = parts[1]
            if "@" in rest:
                creds, host = rest.split("@", 1)
                log_url = f"{scheme}://***:***@{host}"
        except Exception:
            log_url = url
    LOGGER.info("Using database %s", log_url)
    return create_engine(url, echo=echo, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured ``sessionmaker`` bound to the engine."""

    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
