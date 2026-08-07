"""Tests HTTP — sửa map cột trên file đã `parsed` → scoped re-run (WS1-4, ADR #18).

Sửa 1 cột trên file đã `parsed` chỉ chạy lại các check registry báo đọc cột đó
(`run_checks(only=…)`). Finding của check bị ảnh hưởng cập nhật (xoá + dựng lại);
finding của check KHÔNG đọc cột đó giữ nguyên (không treo, trang vẫn render).

Lưu ý cơ chế: từ #84 map cán bộ ÁP THẬT vị trí cột lúc đọc, nên sửa cột là đổi số
liệu. Test ở đây đo SCOPE của re-run chứ không đo số, nên fixture có sẵn cột bản sao
nội dung y hệt: sửa map sang cột bản sao giữ dòng bất biến, phần còn lại chỉ còn là
scope. Chứng minh bằng cách đánh dấu `status=confirmed` trước rồi kiểm check bị ảnh
hưởng về `new` (đã dựng lại) còn check khác giữ `confirmed` (không đụng).
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.models import Company, DataFile, DataFileStatus, Finding
from tests.helpers import drain_jobs, last_job_result

# Header chuẩn NHƯNG cột xuất SX (col 8) nhãn không khớp từ khoá → needs_review → cổng
# review bật (dừng ở `analyzed`), giống test màn review. Điều khiển production_out_qty.
# Hai cột cuối là BẢN SAO nội dung của cột 8 và cột mã: sửa map sang chúng đổi vị
# trí đọc mà KHÔNG đổi số liệu, nên test còn lại đúng một biến là scope re-run.
_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
    "Cột 8 bản sao", "Mã NVL bản sao",
]
_COPY_OF_COL8 = 11
_COPY_OF_CODE = 12


def _m15_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    # MAT0: mất cân đối (10+100-80=30 ≠ 50) → C2.1 fire. C2.3 no (closing>0).
    ws.append([1, "MAT0", "Tên", "KG", 10, 100, 0, 0, 80, 0, 50, 80, "MAT0"])
    # MAT1: cân đối → không fire.
    ws.append([2, "MAT1", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30, 80, "MAT1"])
    # MAT2: cân đối nhưng tồn cuối âm (C2.3 fire) + xuất SX>0 & nhập=0 & tồn đầu=0
    # (C5.1 fire). C2.1 no (0+0-5 = -5 khớp).
    ws.append([3, "MAT2", "Tên", "KG", 0, 0, 0, 0, 5, 0, -5, 5, "MAT2"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _company(app_db) -> None:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_RERUN", name="Rerun", tax_id="1"))
        db.commit()


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _upload_and_parse(client, app_db) -> tuple[int, dict]:
    """Upload (dừng ở `analyzed`) → confirm (advance `parsed`). Trả (file_id, base_map)."""
    r = client.post(
        "/companies/DN_RERUN/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", _m15_bytes(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_RERUN").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ANALYZED
        fid = row.id
        base_map = dict(row.parse_detail_obj["column_map"])
    # Confirm lần đầu (analyzed→parsed): map giữ nguyên, KHÔNG auto chạy check.
    data = {f"col_{f}": str(idx) for f, idx in base_map.items()}
    r = client.post(
        f"/companies/DN_RERUN/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_RERUN").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK
    return fid, base_map


def _seed_findings_confirmed(app_db, company_code: str) -> None:
    """Chạy full checks để có finding, rồi đánh dấu mọi finding `confirmed`."""
    from app.pipeline.run_checks import run_checks
    run_checks(company_code, 2024)
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code=company_code).first()
        for f in db.query(Finding).filter_by(company_id=c.id, period_year=2024).all():
            f.status = "confirmed"
        db.commit()


def _by_check(company_id: int, db) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for f in db.query(Finding).filter_by(company_id=company_id, period_year=2024).all():
        out.setdefault(f.check_code, []).append(f)
    return out


def test_edit_column_reruns_only_affected(app_db):
    client = TestClient(app)
    _login(client)
    _company(app_db)
    fid, base_map = _upload_and_parse(client, app_db)
    _seed_findings_confirmed(app_db, "DN_RERUN")

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_RERUN").first()
        cid = c.id
        before = _by_check(cid, db)
        # Điều kiện tiền đề: cả check bị ảnh hưởng (đọc production_out_qty) và check
        # KHÔNG bị ảnh hưởng đều có finding.
        assert len(before["C2.1"]) == 1  # đọc production_out_qty (sum) → affected
        assert len(before["C5.1"]) == 1  # đọc production_out_qty (individual) → affected
        assert len(before["C2.3"]) == 1  # đọc closing_qty → KHÔNG affected
        c23_id = before["C2.3"][0].id

    # Sửa cột production_out_qty sang cột BẢN SAO trên file đã `parsed`: vị trí
    # đọc đổi (→ scoped re-run) nhưng số liệu bất biến.
    data = {f"col_{f}": str(idx) for f, idx in base_map.items()}
    data["col_production_out_qty"] = str(_COPY_OF_COL8)
    r = client.post(
        f"/companies/DN_RERUN/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    # Re-confirm file đã `parsed` + cột đổi → enqueue re-run scoped → /jobs/{id}.
    # #89: xác nhận cột xong thì về đúng dòng kỳ, không sang trang công việc;
    # bất biến vẫn là lượt nạp ĐƯỢC XẾP (kiểm bằng `drain_jobs()` phía dưới).
    assert "/documents#ky-" in r.headers["location"]
    drain_jobs()

    with app_db.SessionLocal() as db:
        after = _by_check(cid, db)
        # (a) Check bị ảnh hưởng đã chạy lại: finding xoá + dựng lại → status về `new`.
        assert len(after["C2.1"]) == 1
        assert after["C2.1"][0].status == "new"
        assert len(after["C5.1"]) == 1
        assert after["C5.1"][0].status == "new"
        # (b) Check KHÔNG bị ảnh hưởng giữ nguyên finding (id + status không đổi).
        assert len(after["C2.3"]) == 1
        assert after["C2.3"][0].id == c23_id
        assert after["C2.3"][0].status == "confirmed"

    # (b tiếp) Finding của check không chạy lại vẫn render được (evidence resolve).
    assert client.get(f"/findings/{c23_id}").status_code == 200


def test_edit_key_column_reruns_balance_check(app_db):
    """Đổi cột KHOÁ (material_code) → C2.1 phải chạy lại dù registry KHÔNG khai cột mã
    cho C2.1 (guard cột khoá). C2.1 dựng evidence_refs lọc theo material_code; đổi cột
    mã làm khoá đổi → nếu chỉ dựa `checks_reading('m15','material_code')` (không có
    C2.1) thì C2.1 để lại finding treo."""
    from app.checks.registry import checks_reading
    # Tiền đề của guard: C2.1 KHÔNG nằm trong checks_reading cột mã.
    assert "C2.1" not in checks_reading("m15", "material_code")

    client = TestClient(app)
    _login(client)
    _company(app_db)
    fid, base_map = _upload_and_parse(client, app_db)
    _seed_findings_confirmed(app_db, "DN_RERUN")

    with app_db.SessionLocal() as db:
        cid = db.query(Company).filter_by(code="DN_RERUN").first().id
        assert len(_by_check(cid, db)["C2.1"]) == 1

    # Đổi map cột khoá material_code sang cột bản sao (mã y hệt, chỉ đổi vị trí
    # đọc; điểm test là SCOPE re-run gồm C2.1 nhờ guard).
    data = {f"col_{f}": str(idx) for f, idx in base_map.items()}
    data["col_material_code"] = str(_COPY_OF_CODE)
    r = client.post(
        f"/companies/DN_RERUN/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    # #89: xác nhận cột xong thì về đúng dòng kỳ, không sang trang công việc;
    # bất biến vẫn là lượt nạp ĐƯỢC XẾP (kiểm bằng `drain_jobs()` phía dưới).
    assert "/documents#ky-" in r.headers["location"]
    drain_jobs()

    with app_db.SessionLocal() as db:
        after = _by_check(cid, db)
        # Guard đưa C2.1 vào scope → finding C2.1 dựng lại (status về `new`).
        assert len(after["C2.1"]) == 1
        assert after["C2.1"][0].status == "new"


def test_no_column_change_does_not_rerun(app_db):
    client = TestClient(app)
    _login(client)
    _company(app_db)
    fid, base_map = _upload_and_parse(client, app_db)
    _seed_findings_confirmed(app_db, "DN_RERUN")

    with app_db.SessionLocal() as db:
        cid = db.query(Company).filter_by(code="DN_RERUN").first().id
        ids_before = {
            f.id: f.status
            for f in db.query(Finding).filter_by(company_id=cid, period_year=2024).all()
        }

    # Confirm lại KHÔNG đổi cột nào → diff rỗng → KHÔNG chạy lại check nào.
    data = {f"col_{f}": str(idx) for f, idx in base_map.items()}
    r = client.post(
        f"/companies/DN_RERUN/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    # Job nạp lại vẫn chạy (áp map), nhưng KHÔNG nối job chạy kiểm tra.
    drain_jobs()
    assert last_job_result("ingest").get("checks_job_id") is None

    with app_db.SessionLocal() as db:
        ids_after = {
            f.id: f.status
            for f in db.query(Finding).filter_by(company_id=cid, period_year=2024).all()
        }
    # Mọi finding giữ nguyên id + status `confirmed` (không check nào bị dựng lại).
    assert ids_after == ids_before
    assert set(ids_after.values()) == {"confirmed"}
