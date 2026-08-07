"""#95 HTTP — vòng đời xác nhận cột trên file bố cục MỞ RỘNG.

Đường end-to-end phải khép: tải lên → dừng ở cổng review → cán bộ sửa nhóm cột →
nạp lại ĐỌC ĐÚNG nhóm đó → cổng review clear. Trước bản sửa file kẹt ở "cần xác
nhận" vĩnh viễn vì map cán bộ không được áp cho bố cục mở rộng.

Bẫy riêng của đường này: lúc xác nhận, biểu mẫu GHIM luôn trang tính đang đọc. Lượt
nạp sau nhận `sheet` khác None nên nhánh dò bố cục mở rộng bị bỏ qua, và file được
đọc bằng cột cố định — mọi trường lệch, im lặng. Test `officer_group` dưới đây chết
đúng ở đó nếu nhánh ghim trang không thử lại bố cục mở rộng.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.models.job import Job
from app.pipeline.data_files import year_review_gate
from app.pipeline.saved_map import load_column_map
from tests.helpers import XLSX_MIME, drain_jobs, last_job_result

# Bố cục mở rộng như 004: cột `Mã kế toán` chèn ở c1, `Nhập` tách thành `(6a)(6b)`
# và KHÔNG có cột Tổng — trường `import_qty` chỉ đọc được bằng TỔNG hai cột con.
_SUB_A, _SUB_B = 5, 6
_NUMBERING = [
    "(1)", "152", "(2)", None, "(5)", "(6a)", "(6b)", "(7)", "(8)", "(9)", "(10)",
    "(11)=(5)+(6)-(7)-(8)-(9)-(10)",
]


# Hai cột phụ KHÔNG có trên dòng đánh số: `Xuất sản xuất` cũng tách làm hai chứng từ,
# tổng đúng bằng cột (9). Dùng cho ca cán bộ đổi một trường đang đọc MỘT cột sang NHÓM.
_SPLIT_A, _SPLIT_B = 12, 13


def _extended_m15_bytes(split_output: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NPL"
    width = len(_NUMBERING) + (2 if split_output else 0)
    for _ in range(5):
        ws.append([None] * width)
    ws.append([*_NUMBERING, None, None] if split_output else list(_NUMBERING))
    for i in range(3):
        # 10 + (40+60) - 0 - 0 - 80 - 0 = 30 → đẳng thức khớp.
        row = [i + 1, "ACC", f"MAT{i}", None, 10, 40, 60, 0, 0, 80, 0, 30]
        if split_output:
            row += [30, 50]  # 30 + 50 = 80, đúng bằng cột (9)
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _login(client: TestClient) -> None:
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _company(app_db) -> None:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_EXT", name="Ext", tax_id="9"))
        db.commit()


def _upload(client: TestClient, split_output: bool = False) -> None:
    r = client.post(
        "/companies/DN_EXT/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", _extended_m15_bytes(split_output), XLSX_MIME)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()
    assert last_job_result("ingest")["status"] == "needs_review"


def _file_state(app_db) -> tuple[int, dict]:
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EXT").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        return row.id, dict(row.parse_detail_obj)


def _form_data(base_map: dict) -> dict[str, str]:
    """Ô nhập của biểu mẫu: nhóm cột viết dạng danh sách ngăn bởi dấu phẩy."""
    out = {}
    for field, value in base_map.items():
        cols = value if isinstance(value, list) else [value]
        out[f"col_{field}"] = ",".join(str(c) for c in cols)
    return out


def test_extended_file_offers_the_whole_group_on_the_review_screen(app_db):
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload(client)

    fid, detail = _file_state(app_db)
    assert detail["column_map"]["import_qty"] == [_SUB_A, _SUB_B]

    html = client.get(f"/companies/DN_EXT/documents/file/{fid}/review").text
    assert 'name="col_import_qty"' in html
    assert f'value="{_SUB_A},{_SUB_B}"' in html


def test_officer_group_is_applied_and_clears_the_review_gate(app_db):
    """Cán bộ xác nhận (giữ nhóm `(6a)+(6b)`) → nạp thật, đọc đúng nhóm, hết kẹt."""
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload(client)

    fid, detail = _file_state(app_db)
    form_sig = detail["form_signature"]
    data = _form_data(detail["column_map"])
    data["sheet"] = detail["sheet"]  # biểu mẫu gửi kèm trang tính đang đọc

    r = client.post(
        f"/companies/DN_EXT/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/jobs/")
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EXT").first()
        rows = db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).all()
        assert len(rows) == 3
        # Đọc đúng cột mã của bố cục mở rộng (c2), KHÔNG phải `Mã kế toán` ở c1.
        assert {r.material_code for r in rows} == {"MAT0", "MAT1", "MAT2"}
        # Nhập trong kỳ = (6a)+(6b) = 100, không phải 40.
        assert {r.import_qty for r in rows} == {100.0}

        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK
        assert row.parse_detail_obj["review"] == "verified"
        assert row.match_source == "officer-map"
        assert year_review_gate(db, c, 2024) is None

        saved = load_column_map(db, c.id, "m15", form_sig)
        assert saved is not None
        assert saved.column_map_obj["import_qty"] == [_SUB_A, _SUB_B]


def test_officer_may_turn_a_single_column_field_into_a_group(app_db):
    """Trường đang đọc MỘT cột vẫn đổi sang NHÓM được — bố cục của FILE mới quyết định.

    Ràng buộc "mỗi trường một cột" là của bố cục CHUẨN. Bắt nó theo hình dạng hiện tại
    của từng trường thì trên chính file mở rộng, cán bộ muốn dời `Xuất sản xuất` sang
    hai cột chứng từ sẽ nhận một câu từ chối sai — lại đúng kiểu ngõ cụt #95 diệt.
    """
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload(client, split_output=True)

    fid, detail = _file_state(app_db)
    assert detail["column_map"]["production_out_qty"] == [9]

    html = client.get(f"/companies/DN_EXT/documents/file/{fid}/review").text
    assert 'name="col_production_out_qty"' in html
    assert 'type="text"' in html  # ô nhập nhận được danh sách chỉ số

    data = _form_data(detail["column_map"])
    data["col_production_out_qty"] = f"{_SPLIT_A},{_SPLIT_B}"
    data["sheet"] = detail["sheet"]
    r = client.post(
        f"/companies/DN_EXT/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/jobs/")
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EXT").first()
        rows = db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).all()
        assert len(rows) == 3
        # 30 + 50 — cộng cả nhóm; lấy cột đầu thôi thì đẳng thức đã vỡ và không nạp.
        assert {r.production_out_qty for r in rows} == {80.0}
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK
        assert row.parse_detail_obj["column_map"]["production_out_qty"] == [_SPLIT_A, _SPLIT_B]
        assert year_review_gate(db, c, 2024) is None


def test_officer_group_that_breaks_the_balance_is_reported_not_swallowed(app_db):
    """Bỏ `(6b)` khỏi nhóm → đẳng thức vỡ → lượt nạp DỪNG và nói ra, không ghi số sai.

    Không có nhánh nào lặng lẽ đọc lại map suy được rồi báo nạp xong. Và trang xác nhận
    vẫn dựng lại được: căn cứ đọc của lượt trước giữ nguyên nên cán bộ sửa lại chỉ số
    cột được, file không đổi một ngõ cụt này lấy một ngõ cụt khác.
    """
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload(client)

    fid, detail = _file_state(app_db)
    data = _form_data(detail["column_map"])
    data["col_import_qty"] = str(_SUB_A)
    data["sheet"] = detail["sheet"]

    r = client.post(
        f"/companies/DN_EXT/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()

    result = last_job_result("ingest")
    assert result["status"] == "diagnosis_error"
    reported = " ".join(d["title"] + " " + d["detail"] for d in result["diagnostics"])
    assert "đẳng thức" in reported
    assert "import_qty" in reported

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EXT").first()
        # Không dòng nào được ghi.
        assert db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).count() == 0
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ERROR
        # Đường sửa còn nguyên: map cột của lượt đọc trước vẫn ở đó.
        assert row.parse_detail_obj["column_map"]["import_qty"] == [_SUB_A, _SUB_B]

    html = client.get(f"/companies/DN_EXT/documents/file/{fid}/review").text
    assert 'name="col_import_qty"' in html


def test_two_fields_may_not_claim_the_same_column(app_db):
    """Lỗi #84 để lại: biểu mẫu nhận cùng một chỉ số cột cho hai trường."""
    client = TestClient(app)
    _login(client)
    _company(app_db)
    _upload(client)

    fid, detail = _file_state(app_db)
    data = _form_data(detail["column_map"])
    data["col_import_qty"] = str(detail["column_map"]["closing_qty"][0])
    data["sheet"] = detail["sheet"]

    before = _queued_and_saved(app_db)
    r = client.post(
        f"/companies/DN_EXT/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/documents?error=" in r.headers["location"]
    assert _queued_and_saved(app_db) == before  # không xếp job, không ghi map


def _queued_and_saved(app_db) -> tuple[int, int]:
    from app.models.saved_column_map import SavedColumnMap

    with app_db.SessionLocal() as db:
        return db.query(Job).count(), db.query(SavedColumnMap).count()


def test_standard_layout_rejects_a_multi_column_answer(app_db):
    """File bố cục chuẩn đọc mỗi trường bằng MỘT cột — nhận "5,6" ở đó là hứa suông."""
    from tests.helpers import m15_xlsx_bytes

    client = TestClient(app)
    _login(client)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_STD", name="Std", tax_id="8"))
        db.commit()

    header = [
        "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
        "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
    ]
    r = client.post(
        "/companies/DN_STD/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", m15_xlsx_bytes(header), XLSX_MIME)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_STD").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        fid, base_map = row.id, dict(row.parse_detail_obj["column_map"])

    data = _form_data(base_map)
    data["col_production_out_qty"] = "8,9"
    r = client.post(
        f"/companies/DN_STD/documents/file/{fid}/review", data=data, follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/documents?error=" in r.headers["location"]
