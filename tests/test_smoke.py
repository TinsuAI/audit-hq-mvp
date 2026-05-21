# ruff: noqa: I001
import app.models  # noqa: F401  load metadata first (binds `app` to package)
import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app  # then rebind `app` to FastAPI instance


# Smoke tests dùng default engine (audit_hq.sqlite). CI khởi đầu trống nên
# tạo schema 1 lần ở module setup.
@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    Base.metadata.create_all(engine)


client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "build_sha" in body


def test_login_page_renders():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Đăng nhập" in response.text


def test_overview_requires_login():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_then_overview():
    fresh = TestClient(app)
    response = fresh.post(
        "/login",
        data={"user": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    # `/` redirects to `/companies` after login.
    home = fresh.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/companies"

    page = fresh.get("/companies")
    assert page.status_code == 200
    assert "Bảng tổng quan doanh nghiệp" in page.text


def test_login_wrong_password():
    response = client.post(
        "/login",
        data={"user": "admin", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Sai tài khoản" in response.text
