"""Tests HTTP — màn review map cột (WS1-3b, ADR #18).

- GET render map cột đề xuất + badge evidence + ô sửa cột `needs_review` của file `analyzed`.
- POST xác nhận ghi map qua store #6, re-ingest (commit) → file advance `analyzed→parsed`,
  cột resolve `officer-confirmed` → `verified`, cổng review clear.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.pipeline.data_files import year_review_gate
from app.pipeline.saved_map import load_column_map
from tests.conftest import AppDb
from tests.helpers import drain_jobs, last_job_result, upload_and_ingest

# Header Mẫu 15 bố cục chuẩn NHƯNG cột xuất SX (col 8) dùng nhãn không khớp từ khoá
# → `production_out_qty` chỉ `balance-checked`; cột này dùng RIÊNG LẺ (C4.3/C5.1) nên
# `balance-checked` KHÔNG đủ → `needs_review` (đúng để bật cổng review).
_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
]


def _needs_review_m15_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    # Cân đối: 10 + 100 - 0 - 0 - 80 - 0 = 30 → đẳng thức khớp (balance-checked).
    for i in range(3):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_SPARE_COL = 11          # cột phụ ngoài biểu chuẩn, mang giá trị phân biệt được
_SPARE_VALUE = 999.0


def _m15_with_spare_column_bytes() -> bytes:
    """Như trên nhưng thêm một cột phụ — để test cán bộ DỜI cột đọc sang đó."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    header = [*_M15_HEADER, "Ghi chú"]
    for _ in range(8):
        ws.append([None] * len(header))
    ws.append(header)
    for i in range(3):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30, _SPARE_VALUE])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _company(app_db: AppDb) -> None:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_REV", name="Rev", tax_id="1"))
        db.commit()


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _upload_needs_review(client) -> None:
    r = upload_and_ingest(client, "DN_REV", "Mau15_NVL.xlsx", _needs_review_m15_bytes())
    assert r.status_code == 303
    # Nạp chạy ở hàng đợi → redirect tới trang công việc, chưa đọc file lúc request.
    assert r.headers["location"].endswith("/documents#ky-2024")
    drain_jobs()
    # Dừng ở cổng review → job kết luận "cần xác nhận", KHÔNG tự nạp.
    assert last_job_result("ingest")["status"] == "needs_review"


def test_review_get_renders_map_and_badges(app_db: AppDb):
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload_needs_review(client)

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_REV").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ANALYZED  # dừng, chưa parsed
        fid = row.id

    html = client.get(f"/companies/DN_REV/documents/file/{fid}/review").text
    assert "Xuất sản xuất" in html          # nhãn field production_out_qty
    # Căn cứ của cột balance-checked hiện thành CÂU, và câu đó phải mang GIỚI HẠN của
    # cơ chế (#120) — thuật ngữ trần "Khớp đẳng thức" không nói được khi nào không tin được.
    assert "không phân biệt hai cột cùng dấu" in html
    assert "Cần xác nhận" in html            # trạng thái review cột
    assert 'name="col_production_out_qty"' in html  # ô sửa cột needs_review


def test_review_confirm_saves_map_and_advances_to_parsed(app_db: AppDb):
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload_needs_review(client)

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_REV").first()
        cid = c.id
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        fid = row.id
        detail = row.parse_detail_obj
        form_sig = detail["form_signature"]
        base_map = detail["column_map"]
        # Trước xác nhận: cổng review còn bật.
        assert year_review_gate(db, c, 2024) is not None
        # Chưa commit dòng nào (dry-run).
        assert db.query(NvlBalance).filter_by(company_id=cid, period_year=2024).count() == 0

    data = {f"col_{field}": str(idx) for field, idx in base_map.items()}
    r = client.post(
        f"/companies/DN_REV/documents/file/{fid}/review",
        data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/documents#ky-2024")
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_REV").first()
        saved = load_column_map(db, c.id, "m15", form_sig)
        assert saved is not None
        assert saved.column_map_obj == base_map
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK  # advance analyzed→parsed
        assert row.parse_detail_obj["review"] == "verified"  # officer-confirmed
        # Cổng review đã clear + dòng dữ liệu đã commit.
        assert year_review_gate(db, c, 2024) is None
        assert db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).count() == 3


def test_confirming_a_moved_column_reads_the_officer_column(app_db: AppDb):
    """Cán bộ sửa chỉ số cột → lượt nạp kế ĐỌC ĐÚNG cột đó (#84, ADR #24 mục 5).

    Trước bản sửa, map lưu chỉ nâng NHÃN bằng chứng lên `officer-confirmed`; adapter
    vẫn đọc cột cũ, nên số liệu Tầng 1 không đổi và cán bộ tin là đã sửa xong trong
    khi hệ thống vẫn đọc sai — im lặng.
    """
    client = TestClient(app)
    _login(client)
    _company(app_db)
    r = upload_and_ingest(
        client, "DN_REV", "Mau15_NVL.xlsx", _m15_with_spare_column_bytes()
    )
    assert r.status_code == 303
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_REV").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        fid, base_map = row.id, dict(row.parse_detail_obj["column_map"])
        assert base_map["closing_qty"] != _SPARE_COL  # tiền đề: đang đọc cột chuẩn

    data = {f"col_{field}": str(idx) for field, idx in base_map.items()}
    data["col_closing_qty"] = str(_SPARE_COL)
    r = client.post(
        f"/companies/DN_REV/documents/file/{fid}/review",
        data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_REV").first()
        rows = db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).all()
        assert len(rows) == 3
        # Số liệu đọc từ ĐÚNG cột cán bộ chỉ, không phải cột chuẩn (30).
        assert {r.closing_qty for r in rows} == {_SPARE_VALUE}
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK
        assert row.match_source == "officer-map"
        assert row.parse_detail_obj["column_map"]["closing_qty"] == _SPARE_COL
