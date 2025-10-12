"""Pytest configuration and fixtures for smoke tests."""
import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from python import models, db
from python.repository import Repository


@pytest.fixture(scope="session")
def database_url():
    """Get database URL from environment or default to SQLite."""
    return db.build_database_url()


@pytest.fixture(scope="session")
def engine(database_url):
    """Create database engine for tests."""
    return create_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )


@pytest.fixture(scope="session")
def setup_database(engine):
    """Create all tables before tests run."""
    models.Base.metadata.create_all(engine)
    yield


@pytest.fixture
def session_factory(engine, setup_database):
    """Create a session factory for tests."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def session(session_factory):
    """Create a new database session for each test."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def repo(session):
    """Create a repository instance for each test."""
    return Repository(session)
