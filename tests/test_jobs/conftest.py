"""Shared fixtures cho test_jobs/*.

Dùng SQLite in-memory với schema từ Base.metadata. Tách khỏi tests/conftest.py
vì test_jobs không cần seed UOM data; có cần seed User để FK tests.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import User
from app.models.user import ROLE_ADMIN


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Local() as s:
        yield s
        s.rollback()


@pytest.fixture
def admin_user(session: Session) -> User:
    u = User(username="admin", password_hash="x", role=ROLE_ADMIN)
    session.add(u)
    session.commit()
    return u
