from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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

    home = fresh.get("/")
    assert home.status_code == 200
    assert "Tổng quan doanh nghiệp" in home.text


def test_login_wrong_password():
    response = client.post(
        "/login",
        data={"user": "admin", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Sai tài khoản" in response.text
