"""Lỗi phải ra trang tiếng Việt cho trình duyệt, JSON cho mã gọi API (issue #94).

Trước đây ứng dụng không đăng ký một trình xử lý lỗi nào, nên mọi lỗi — gõ sai mã
DN, tham số rỗng, lỗi hệ thống — đều đổ JSON của framework thẳng ra màn hình cán bộ.
Hai điểm cuối JSON (`overview.json`, `unread.json`) có JavaScript đang poll: chúng
PHẢI giữ JSON kể cả khi trình duyệt gửi `Accept: text/html`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company

# Trình duyệt điều hướng gửi `text/html`; `fetch()` mặc định gửi `*/*`.
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
API = {"Accept": "*/*"}

# Chuỗi của framework / dấu vết ngăn xếp không bao giờ được ra màn hình.
LEAKS = ('int_parsing', 'Input should be', 'Traceback', 'RuntimeError', '"loc"', 'Not Found')

BOOM_PATH = "/_test-94-loi-noi-bo"
BOOM_HTTP_PATH = "/_test-94-loi-noi-bo-http"
BOOM_SECRET = "MST 0101234567 cua DN nhay cam"


@app.get(BOOM_PATH)
def _boom_for_tests() -> dict:
    """Route dùng riêng cho test — lỗi ngoài dự kiến không được lộ nội dung ra ngoài."""
    raise RuntimeError(BOOM_SECRET)


@app.get(BOOM_HTTP_PATH)
def _boom_http_for_tests() -> dict:
    """Nhánh thứ hai của lỗi 500: `HTTPException(500, detail=…)`.

    `companies.py` có chỗ raise `HTTPException(500, detail=f"Lưu file lỗi: {e}")` —
    câu kèm theo chứa đường dẫn và thông điệp của hệ điều hành, không được ra màn hình.
    """
    from fastapi import HTTPException

    raise HTTPException(status_code=500, detail=BOOM_SECRET)


def _setup():
    import app.database as dbmod
    from app.auth_users import create_user, seed_default_admin
    from app.models import user_companies

    eng = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    ses = dbmod.sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    dbmod.engine, dbmod.SessionLocal = eng, ses
    Base.metadata.create_all(eng)
    with ses() as db:
        seed_default_admin(db, "admin", "admin")
        off = create_user(db, "canbo", "matkhau123", "officer")
        trong = Company(code="DN_TRONG", tax_id="1000000001", name="DN trong phạm vi")
        ngoai = Company(code="DN_NGOAI", tax_id="1000000002", name="DN ngoài phạm vi")
        db.add_all([trong, ngoai])
        db.flush()
        db.execute(user_companies.insert().values(user_id=off.id, company_id=trong.id))
        db.commit()
    return eng


def _teardown(eng):
    import app.database as dbmod

    eng.dispose()
    dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


@pytest.fixture
def db_engine():
    eng = _setup()
    try:
        yield eng
    finally:
        _teardown(eng)


def _login(client: TestClient, user: str = "admin", password: str = "admin") -> None:
    r = client.post("/login", data={"user": user, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text


@pytest.fixture
def client(db_engine):
    c = TestClient(app)
    _login(c)
    return c


@pytest.fixture
def officer(db_engine):
    c = TestClient(app)
    _login(c, "canbo", "matkhau123")
    return c


def _is_html(r) -> bool:
    return r.headers["content-type"].startswith("text/html")


def _is_json(r) -> bool:
    return r.headers["content-type"].startswith("application/json")


def _assert_no_leak(text: str) -> None:
    for token in LEAKS:
        assert token not in text, f"chuỗi nội bộ “{token}” lọt ra giao diện"


# --- Tham số số nguyên rỗng = không truyền -----------------------------------


@pytest.mark.parametrize("qs", ["year=", "page=", "ingested=", "year=&page=&ingested="])
def test_empty_integer_query_params_are_treated_as_absent(client, qs):
    """`?year=` là liên kết do chính giao diện dựng ra — không được thành lỗi."""
    r = client.get(f"/companies/DN_TRONG?{qs}", headers=BROWSER)
    assert r.status_code == 200, r.text[:300]
    assert _is_html(r)
    assert "DN trong phạm vi" in r.text


def test_empty_optional_string_param_keeps_working(client):
    """Tham số chuỗi không nằm trong diện xử lý — trang vẫn mở bình thường."""
    r = client.get("/companies/DN_TRONG?check=&book=", headers=BROWSER)
    assert r.status_code == 200
    assert _is_html(r)


# --- Lỗi kiểm kiểu tham số ----------------------------------------------------


def test_non_numeric_year_gives_vietnamese_html_page_to_browser(client):
    r = client.get("/companies/DN_TRONG?year=abc", headers=BROWSER)
    assert r.status_code == 422
    assert _is_html(r)
    _assert_no_leak(r.text)
    assert "không hợp lệ" in r.text
    assert 'href="/companies"' in r.text          # đường quay lại


def test_non_numeric_year_still_gives_json_to_api_client(client):
    r = client.get("/companies/DN_TRONG?year=abc", headers=API)
    assert r.status_code == 422
    assert _is_json(r)


# --- HTTPException: 404 · 403 -------------------------------------------------


def test_unknown_company_code_gives_html_404_to_browser(client):
    r = client.get("/companies/KHONG_CO_MA_NAY", headers=BROWSER)
    assert r.status_code == 404
    assert _is_html(r)
    _assert_no_leak(r.text)
    assert 'href="/companies"' in r.text


def test_out_of_scope_company_gives_html_404_to_browser(officer):
    """DN ngoài phạm vi trả 404 cố ý (app/scoping.py) — vẫn phải là trang HTML."""
    r = officer.get("/companies/DN_NGOAI", headers=BROWSER)
    assert r.status_code == 404
    assert _is_html(r)
    _assert_no_leak(r.text)


def test_forbidden_gives_html_403_to_browser(officer):
    r = officer.get("/admin/audit", headers=BROWSER)
    assert r.status_code == 403
    assert _is_html(r)
    _assert_no_leak(r.text)
    assert 'href="/companies"' in r.text


def test_bad_request_gives_html_400_to_browser(client):
    r = client.get("/companies/DN_TRONG/data?year=2024&table=khong_co", headers=BROWSER)
    assert r.status_code == 400
    assert _is_html(r)
    _assert_no_leak(r.text)
    assert 'href="/companies"' in r.text


def test_missing_document_gives_html_404_to_browser(client):
    r = client.get("/companies/DN_TRONG/documents/file/999999/preview", headers=BROWSER)
    assert r.status_code == 404
    assert _is_html(r)
    _assert_no_leak(r.text)


def test_empty_value_for_a_required_integer_param_gives_html_not_raw_json(client):
    """`year` bắt buộc: chuỗi rỗng thành thiếu tham số, vẫn phải ra trang tiếng Việt."""
    r = client.get("/companies/DN_TRONG/data?year=&table=m15", headers=BROWSER)
    assert r.status_code == 422
    assert _is_html(r)
    _assert_no_leak(r.text)


def test_out_of_range_integer_param_gives_html_page(client):
    """`page` có ràng buộc `ge=1` — lỗi ràng buộc cũng phải ra trang, không đổ JSON."""
    r = client.get("/companies/DN_TRONG/data?year=2024&table=m15&page=0", headers=BROWSER)
    assert r.status_code == 422
    assert _is_html(r)
    _assert_no_leak(r.text)


def test_empty_constrained_integer_param_falls_back_to_default(client):
    r = client.get("/companies/DN_TRONG/data?year=2024&table=m15&page=&full=", headers=BROWSER)
    assert r.status_code == 200
    assert _is_html(r)


def test_unknown_path_gives_html_404_without_english_phrase(client):
    r = client.get("/duong-dan-hoan-toan-khong-ton-tai", headers=BROWSER)
    assert r.status_code == 404
    assert _is_html(r)
    _assert_no_leak(r.text)


def test_unknown_company_code_gives_json_to_api_client(client):
    r = client.get("/companies/KHONG_CO_MA_NAY", headers=API)
    assert r.status_code == 404
    assert _is_json(r)


# --- Điểm cuối JSON phải giữ JSON kể cả khi trình duyệt hỏi HTML --------------


def test_overview_json_keeps_json_on_validation_error(client):
    """JavaScript ở overview-poll.js đọc `.json()` — trả HTML là poll hỏng im lặng."""
    r = client.get(
        "/companies/DN_TRONG/overview.json?year=&check=C1.1", headers=BROWSER
    )
    assert r.status_code == 422
    assert _is_json(r)


def test_overview_json_keeps_json_on_not_found(client):
    r = client.get(
        "/companies/KHONG_CO_MA_NAY/overview.json?year=2024&check=C1.1", headers=BROWSER
    )
    assert r.status_code == 404
    assert _is_json(r)


def test_unread_json_keeps_json_on_error(client):
    r = client.post("/jobs/unread.json", headers=BROWSER)
    assert r.status_code == 405
    assert _is_json(r)


def test_chat_api_keeps_json_on_error(client):
    """Sidebar trợ lý gọi `/api/chat/*` bằng fetch — nhánh lỗi phải là JSON."""
    r = client.get("/api/chat/conversations?company_id=abc", headers=BROWSER)
    assert r.status_code == 400
    assert _is_json(r)


# --- Lỗi 500 ------------------------------------------------------------------


def test_internal_error_hides_details_from_browser(db_engine):
    c = TestClient(app, raise_server_exceptions=False)
    _login(c)
    r = c.get(BOOM_PATH, headers=BROWSER)
    assert r.status_code == 500
    assert _is_html(r)
    assert BOOM_SECRET not in r.text
    _assert_no_leak(r.text)
    assert 'href="/companies"' in r.text


def test_internal_error_hides_details_from_api_client(db_engine):
    c = TestClient(app, raise_server_exceptions=False)
    _login(c)
    r = c.get(BOOM_PATH, headers=API)
    assert r.status_code == 500
    assert _is_json(r)
    assert BOOM_SECRET not in r.text
    assert "Traceback" not in r.text


def test_http_exception_500_does_not_show_its_detail_to_the_browser(client):
    r = client.get(BOOM_HTTP_PATH, headers=BROWSER)
    assert r.status_code == 500
    assert _is_html(r)
    assert BOOM_SECRET not in r.text
    _assert_no_leak(r.text)
    assert 'href="/companies"' in r.text


def test_http_exception_500_does_not_show_its_detail_to_the_api_client(client):
    r = client.get(BOOM_HTTP_PATH, headers=API)
    assert r.status_code == 500
    assert _is_json(r)
    assert BOOM_SECRET not in r.text


# --- Chuyển hướng đăng nhập không được biến thành trang lỗi -------------------


def test_anonymous_request_still_redirects_to_login(db_engine):
    c = TestClient(app)
    r = c.get("/companies/DN_TRONG", headers=BROWSER, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- Nguồn sinh ra URL hỏng ---------------------------------------------------


def test_job_detail_never_builds_a_link_with_an_empty_year(client):
    """Công việc không gắn kỳ → liên kết phải bỏ hẳn tham số, không để `?year=`."""
    import app.database as dbmod
    from app.auth_users import get_user_by_username
    from app.models.job import Job, JobKind, JobStatus

    with dbmod.SessionLocal() as db:
        admin = get_user_by_username(db, "admin")
        job = Job(
            kind=JobKind.RUN_CHECKS.value,
            payload={"company_code": "DN_TRONG"},
            status=JobStatus.DONE.value,
            result={"findings": 0},
            created_by=admin.id,
            period_year=None,
        )
        db.add(job)
        db.commit()
        job_id = job.id

    r = client.get(f"/jobs/{job_id}", headers=BROWSER)
    assert r.status_code == 200
    assert "?year=\"" not in r.text
    assert "?year=&" not in r.text
    assert "/companies/DN_TRONG" in r.text
