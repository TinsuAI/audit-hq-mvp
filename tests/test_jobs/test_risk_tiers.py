"""Test ngưỡng hạng rủi ro configurable."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.app_settings as appset
import app.database as dbmod
from app.auth_users import seed_default_admin
from app.database import Base, SessionLocal, engine
from app.main import app


def _setup_db():
    new_engine = dbmod.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True,
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
    appset.invalidate_cache()
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    appset.invalidate_cache()


def _login(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False,
    )
    assert r.status_code == 303


def test_default_uppers_match_user_spec():
    """Mặc định theo yêu cầu: 50, 100, 300, 600, 1000."""
    assert appset.DEFAULT_RISK_TIER_UPPERS == (50, 100, 300, 600, 1000)


def test_get_uppers_returns_default_when_empty():
    new_engine, _ = _setup_db()
    try:
        assert appset.get_risk_tier_uppers() == (50, 100, 300, 600, 1000)
    finally:
        _teardown(new_engine)


def test_save_and_read_back():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            appset.save_risk_tier_uppers([30, 80, 200, 500, 1000], "admin", db)
        # Cache invalidated → đọc lại từ DB.
        assert appset.get_risk_tier_uppers() == (30, 80, 200, 500, 1000)
    finally:
        _teardown(new_engine)


def test_validation_rejects_bad_inputs():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            # Sai số lượng.
            with pytest.raises(appset.ValidationError):
                appset.save_risk_tier_uppers([10, 20, 30, 40], "admin", db)
            # Không tăng dần.
            with pytest.raises(appset.ValidationError):
                appset.save_risk_tier_uppers([100, 50, 200, 500, 1000], "admin", db)
            # Cuối khác 1000.
            with pytest.raises(appset.ValidationError):
                appset.save_risk_tier_uppers([50, 100, 300, 600, 900], "admin", db)
            # Âm.
            with pytest.raises(appset.ValidationError):
                appset.save_risk_tier_uppers([-1, 100, 300, 600, 1000], "admin", db)
    finally:
        _teardown(new_engine)


def test_scoring_tier_uses_dynamic_uppers():
    """Đổi ngưỡng → tier_for() trả nhãn theo ngưỡng mới ngay."""
    from app.checks.scoring import tier_for

    new_engine, new_session = _setup_db()
    try:
        # Default: 50, 100, 300, 600, 1000.
        # Score 60 → "Có chênh lệch nhỏ" (50 < 60 <= 100).
        assert tier_for(60) == "Có chênh lệch nhỏ"
        # Score 40 → "Dữ liệu nhất quán" (<= 50).
        assert tier_for(40) == "Dữ liệu nhất quán"

        # Đổi sang ngưỡng rộng hơn cho hạng 1.
        with new_session() as db:
            appset.save_risk_tier_uppers([100, 200, 400, 700, 1000], "admin", db)

        # Score 60 → giờ thuộc hạng 1 (<= 100).
        assert tier_for(60) == "Dữ liệu nhất quán"
    finally:
        _teardown(new_engine)


def test_admin_page_requires_auth():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        r = client.get("/admin/risk-tiers", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
    finally:
        _teardown(new_engine)


def test_admin_page_renders():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/admin/risk-tiers")
        assert r.status_code == 200
        text = r.text
        assert "Ngưỡng hạng rủi ro" in text
        # 5 default values.
        for v in [50, 100, 300, 600, 1000]:
            assert str(v) in text
        # 5 nhãn.
        for label in [
            "Dữ liệu nhất quán",
            "Có chênh lệch nhỏ",
            "Cần rà soát",
            "Có dấu hiệu bất thường",
            "Bất thường nghiêm trọng",
        ]:
            assert label in text
    finally:
        _teardown(new_engine)


def test_admin_save_form_updates_db():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/admin/risk-tiers",
            data={
                "upper_1": "30",
                "upper_2": "80",
                "upper_3": "200",
                "upper_4": "500",
                "upper_5": "1000",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/admin/risk-tiers" in r.headers["location"]
        assert appset.get_risk_tier_uppers() == (30, 80, 200, 500, 1000)
    finally:
        _teardown(new_engine)


def test_admin_save_invalid_shows_error():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/admin/risk-tiers",
            data={
                "upper_1": "100",
                "upper_2": "50",  # giảm — invalid
                "upper_3": "200",
                "upper_4": "500",
                "upper_5": "1000",
            },
        )
        assert r.status_code == 200
        assert "tăng dần" in r.text
    finally:
        _teardown(new_engine)


def test_admin_reset_restores_default():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            appset.save_risk_tier_uppers([30, 80, 200, 500, 1000], "admin", db)
        assert appset.get_risk_tier_uppers() == (30, 80, 200, 500, 1000)

        client = TestClient(app)
        _login(client)
        r = client.post("/admin/risk-tiers/reset", follow_redirects=False)
        assert r.status_code == 303
        assert appset.get_risk_tier_uppers() == (50, 100, 300, 600, 1000)
    finally:
        _teardown(new_engine)


def test_navbar_has_risk_tiers_link():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies")
        assert 'href="/admin/risk-tiers"' in r.text
    finally:
        _teardown(new_engine)
