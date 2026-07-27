"""Tests cho multi-user auth: password hashing, verify, seed, create."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth_users import (
    authenticate,
    count_admins,
    create_user,
    hash_password,
    seed_default_admin,
    verify_password,
)
from app.database import Base


@pytest.fixture
def user_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Local() as s:
        yield s


# --- hash / verify ---

def test_hash_roundtrip():
    h = hash_password("secret123")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_hash_unique_salts():
    h1 = hash_password("abc")
    h2 = hash_password("abc")
    assert h1 != h2  # different salts


def test_verify_empty_password():
    assert not verify_password("", "anything")
    assert not verify_password("ok", "")


def test_verify_bad_format():
    assert not verify_password("ok", "not_a_real_hash")


# --- create_user ---

def test_create_user_ok(user_session: Session):
    u = create_user(user_session, "alice", "pass1234", "officer")
    user_session.commit()
    assert u.username == "alice"
    assert u.role == "officer"
    assert verify_password("pass1234", u.password_hash)


def test_create_user_duplicate(user_session: Session):
    create_user(user_session, "bob", "pass1234", "admin")
    user_session.commit()
    with pytest.raises(ValueError, match="đã tồn tại"):
        create_user(user_session, "bob", "other", "officer")


def test_create_user_invalid_role(user_session: Session):
    with pytest.raises(ValueError, match="Vai trò không hợp lệ"):
        create_user(user_session, "carol", "pass1234", "superadmin")


# --- authenticate ---

def test_authenticate_ok(user_session: Session):
    create_user(user_session, "dave", "mypass99", "admin")
    user_session.commit()
    u = authenticate(user_session, "dave", "mypass99")
    assert u is not None
    assert u.username == "dave"


def test_authenticate_wrong_password(user_session: Session):
    create_user(user_session, "eve", "correct", "officer")
    user_session.commit()
    assert authenticate(user_session, "eve", "wrong") is None


def test_authenticate_unknown_user(user_session: Session):
    assert authenticate(user_session, "ghost", "anything") is None


# --- seed_default_admin ---

def test_seed_default_admin_first_time(user_session: Session):
    seeded = seed_default_admin(user_session, "admin", "admin")
    assert seeded is not None
    assert seeded.role == "admin"
    assert count_admins(user_session) == 1


def test_seed_default_admin_idempotent(user_session: Session):
    seed_default_admin(user_session, "admin", "admin")
    result2 = seed_default_admin(user_session, "admin2", "pass")
    assert result2 is None  # không seed lần 2


# --- count_admins ---

def test_count_admins(user_session: Session):
    assert count_admins(user_session) == 0
    create_user(user_session, "a1", "pass", "admin")
    create_user(user_session, "o1", "pass", "officer")
    user_session.commit()
    assert count_admins(user_session) == 1
