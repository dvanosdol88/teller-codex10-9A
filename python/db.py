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
    
    Normalizes postgres:// URLs to postgresql+psycopg:// for SQLAlchemy 2.0
    compatibility with the psycopg driver.
    """

    url = os.getenv("DATABASE_INTERNAL_URL")
    if url:
        # Normalize postgres:// to postgresql+psycopg:// for psycopg driver
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            # Also handle postgresql:// without explicit driver
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        
        # Render also supplies DATABASE_SSLMODE which we surface as a query (important-comment)
        # parameter when present.
        sslmode = os.getenv("DATABASE_SSLMODE")
        if sslmode:
            connector = "?" if "?" not in url else "&"
            url = f"{url}{connector}sslmode={sslmode}"
        return url

    return os.getenv("DATABASE_URL", "sqlite:///teller.db")


def create_db_engine(echo: bool = False) -> Engine:
    """Create the SQLAlchemy engine with connection pooling configured for Render.
    
    Connection pool parameters are tuned for Render's starter tier limits:
    - pool_size=5: Maximum connections kept in the pool
    - max_overflow=5: Additional connections allowed beyond pool_size
    - pool_pre_ping=True: Verify connections before use (handles stale connections)
    - pool_recycle=300: Recycle connections after 5 minutes to prevent timeouts
    """

    url = build_database_url()
    LOGGER.info("Using database %s", url)
    
    return create_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )


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
