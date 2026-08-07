"""Test bảo vệ: chạy hàng đợi qua fixture `app_db` KHÔNG ghi vào DB của máy.

`app/pipeline/ingest.py` giữ `SessionLocal` bằng `from app.database import ...`
ở mức module, tức chụp đối tượng ngay lúc import. Vá `app.database.SessionLocal`
một mình KHÔNG đổi được bản sao đó: job nạp vẫn mở phiên tới DB thật của máy dev
và ghi doanh nghiệp cùng dòng Tầng 1 vào đó. Khi ấy khẳng định kiểu "chưa có
dòng nào" trong test XANH VÌ LÝ DO SAI.

Test này chạy trọn một lượt nạp qua hàng đợi, khẳng định dòng đã vào DB tạm, rồi
đối chiếu số bản ghi của DB máy trước/sau. Hai vế phải cùng đúng: chỉ đối chiếu
DB máy thì job hỏng ngay từ đầu cũng cho kết quả "không đổi".
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.main import app
from app.models import Company, NvlBalance
from tests.conftest import AppDb
from tests.helpers import drain_jobs, last_job_result, m15_xlsx_bytes, upload_and_ingest

_COMPANY_CODE = "DN_FIXTURE_GUARD"

# Bảng mà một lượt nạp chắc chắn chạm tới nếu nó ghi nhầm chỗ.
_WATCHED_TABLES = ("companies", "company_periods", "data_files", "nvl_balances", "jobs")


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in _WATCHED_TABLES
        }


def _company_exists(engine: Engine, code: str) -> bool:
    with engine.connect() as conn:
        stmt = text("SELECT count(*) FROM companies WHERE code = :code")
        return conn.execute(stmt, {"code": code}).scalar_one() > 0


def test_ingest_through_the_queue_stays_in_the_fixture_db(app_db: AppDb, default_engine: Engine):
    before = _row_counts(default_engine)

    with app_db.SessionLocal() as db:
        db.add(Company(code=_COMPANY_CODE, name="Fixture Guard", tax_id="1"))
        db.commit()

    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    r = upload_and_ingest(client, _COMPANY_CODE, "Mau15_NVL.xlsx", m15_xlsx_bytes())
    assert r.status_code == 303
    assert drain_jobs() > 0, "phải có job chạy — không chạy thì test này không chứng minh gì"

    # Vế 1: lượt nạp phải THÀNH CÔNG, nếu không thì vế 2 đúng vì lý do sai.
    assert last_job_result("ingest")["status"] == "ok"
    with app_db.SessionLocal() as db:
        company = db.query(Company).filter_by(code=_COMPANY_CODE).first()
        assert db.query(NvlBalance).filter_by(company_id=company.id).count() == 3

    # Vế 2: DB của máy không nhận thêm bản ghi nào.
    assert not _company_exists(default_engine, _COMPANY_CODE)
    assert _row_counts(default_engine) == before
