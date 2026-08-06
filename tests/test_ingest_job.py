"""Nạp dữ liệu chạy ở hàng đợi, không trong request (job `ingest`).

Cloudflare cắt kết nối ở 100 giây, mà một lượt tải lên đọc file mất vài phút với
bộ dữ liệu thật (BCCT 68MB của 006: 97 giây một lượt đọc, ba lượt một lần tải).
Test giữ: request chỉ lưu file rồi xếp job; job chạy mới sinh dòng; và mọi kết
luận của job (chẩn đoán lỗi, dừng chờ xác nhận, kế hoạch sổ sai) đều có nhãn để
hiện lên trang công việc thay vì biến mất cùng redirect.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.database import Base, SessionLocal, engine
from app.jobs.result_labels import RESULT_LABEL_VI
from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.models.job import Job, JobStatus
from app.settings import settings
from tests.helpers import drain_jobs, last_job_result

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]
# Cột 8 nhãn không khớp từ khoá → `production_out_qty` chỉ balance-checked → needs_review.
_M15_HEADER_NEEDS_REVIEW = [*_M15_HEADER[:8], "Cột 8", *_M15_HEADER[9:]]


def _m15_bytes(header: list[str] = _M15_HEADER, rows: int = 3) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(header))
    ws.append(header)
    for i in range(rows):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _setup(tmp_path: Path):
    import app.pipeline.ingest as ingmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_JOB", name="Job", tax_id="1"))
        db.commit()
    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)
    return new_engine, prev_root


def _teardown(new_engine, prev_root):
    import app.pipeline.ingest as ingmod
    settings.raw_data_path = prev_root
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    ingmod.SessionLocal = SessionLocal


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _upload(client, content: bytes, code: str = "DN_JOB", year: int = 2024):
    return client.post(
        f"/companies/{code}/upload",
        data={"year": str(year)},
        files={"m15": ("Mau15_NVL.xlsx", content,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )


def _labels_ok(result: dict) -> bool:
    return set(result) <= set(RESULT_LABEL_VI)


def test_upload_request_only_queues_a_job(tmp_path):
    """Request KHÔNG đọc file: file đã lưu + job queued, chưa dòng nào vào DB."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        r = _upload(client, _m15_bytes())

        assert r.status_code == 303
        assert r.headers["location"].startswith("/jobs/")

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            job = db.query(Job).order_by(Job.id.desc()).first()
            assert job.kind == "ingest"
            assert job.status == JobStatus.QUEUED.value
            assert job.payload["company_code"] == "DN_JOB"
            assert job.payload["year"] == 2024
            assert job.payload["gate"] is True
            # File đã lưu + đăng ký, nhưng chưa parse → chưa có dòng Tầng 1.
            assert db.query(DataFile).filter_by(company_id=c.id, slot="m15").count() == 1
            assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0

        drain_jobs()
        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 3
    finally:
        _teardown(new_engine, prev_root)


def test_job_result_reports_rows_and_has_labels(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client, _m15_bytes())
        drain_jobs()

        res = last_job_result("ingest")
        assert res["status"] == "ok"
        assert res["m15_rows"] == 3
        assert res["bcct_rows"] == 0
        assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"
    finally:
        _teardown(new_engine, prev_root)


def test_unreadable_file_reports_diagnosis_on_the_job(tmp_path):
    """File sai mẫu: job DONE kèm danh sách chẩn đoán (trước đây là trang 422)."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        # Workbook hợp lệ nhưng không có biểu Mẫu 15 nào → chẩn đoán báo lỗi.
        wb = Workbook()
        wb.active.append(["không", "phải", "mẫu", "15"])
        buf = io.BytesIO()
        wb.save(buf)
        _upload(client, buf.getvalue())
        drain_jobs()

        res = last_job_result("ingest")
        assert res["status"] == "diagnosis_error"
        assert res["diagnostics"], "phải nêu được lỗi cụ thể cho cán bộ"
        assert {"slot", "level", "title", "detail"} <= set(res["diagnostics"][0])
        assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0
    finally:
        _teardown(new_engine, prev_root)


def test_job_page_renders_the_diagnosis(tmp_path):
    """Chẩn đoán phải ĐỌC ĐƯỢC trên trang công việc — trước đây nó nằm ở trang 422."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        wb = Workbook()
        wb.active.append(["không", "phải", "mẫu", "15"])
        buf = io.BytesIO()
        wb.save(buf)
        r = _upload(client, buf.getvalue())
        job_url = r.headers["location"]
        drain_jobs()

        html = client.get(job_url).text
        assert "Dữ liệu chưa nạp được" in html
        assert "không chọn được sheet đúng biểu" in html   # tiêu đề chẩn đoán cụ thể
        assert "Nhờ AI chẩn đoán" in html      # lối thoát AI vẫn tới được
        assert "/companies/DN_JOB/documents" in html
    finally:
        _teardown(new_engine, prev_root)


def test_gate_stops_before_writing_rows(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client, _m15_bytes(_M15_HEADER_NEEDS_REVIEW))
        drain_jobs()

        res = last_job_result("ingest")
        assert res["status"] == "needs_review"
        assert res["review_columns"], "phải nêu cột nào cần xác nhận"
        assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            assert row.parse_status == DataFileStatus.ANALYZED
            assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0
    finally:
        _teardown(new_engine, prev_root)


def test_reingest_button_does_not_stop_at_the_gate(tmp_path):
    """"Nạp lại dữ liệu" chạy với gate=False — cán bộ vừa quyết định xong ở trang tài liệu."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client, _m15_bytes(_M15_HEADER_NEEDS_REVIEW))
        drain_jobs()
        assert last_job_result("ingest")["status"] == "needs_review"

        r = client.post(
            "/companies/DN_JOB/documents/ingest", data={"year": "2024"}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/jobs/")
        with dbmod.SessionLocal() as db:
            job = db.query(Job).order_by(Job.id.desc()).first()
            assert job.payload["gate"] is False
        drain_jobs()

        assert last_job_result("ingest")["status"] == "ok"
        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 3
    finally:
        _teardown(new_engine, prev_root)


def test_failed_ingest_does_not_chain_check_job(tmp_path):
    """Nạp hỏng thì KHÔNG nối job kiểm tra — chạy kiểm tra trên dữ liệu cũ là sai lệch."""
    from app.jobs.handlers import ingest_handler

    new_engine, prev_root = _setup(tmp_path)
    try:
        bcqt = tmp_path / "DN_JOB" / "2024" / "BCQT"
        bcqt.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        wb.active.append(["không", "phải", "mẫu", "15"])
        buf = io.BytesIO()
        wb.save(buf)
        (bcqt / "M15_NVL_2024.xlsx").write_bytes(buf.getvalue())

        with dbmod.SessionLocal() as db:
            res = ingest_handler(
                {
                    "company_code": "DN_JOB", "year": 2024, "gate": False,
                    "created_by": 1, "then_run_checks": {"only": None},
                },
                db,
            )
            assert res["status"] == "diagnosis_error"
            assert "checks_job_id" not in res
            assert db.query(Job).filter_by(kind="run_checks").count() == 0
    finally:
        _teardown(new_engine, prev_root)


def test_confirm_review_chains_a_check_job_after_ingest(tmp_path):
    """Sửa cột trên file đã parsed: job nạp chạy trước, job kiểm tra do nó xếp ra sau."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client, _m15_bytes(_M15_HEADER_NEEDS_REVIEW))
        drain_jobs()

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_JOB").first()
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            fid, base_map = row.id, dict(row.parse_detail_obj["column_map"])

        # Lần confirm đầu (analyzed→parsed): chưa có finding nên KHÔNG nối job kiểm tra.
        data = {f"col_{f}": str(i) for f, i in base_map.items()}
        client.post(f"/companies/DN_JOB/documents/file/{fid}/review",
                    data=data, follow_redirects=False)
        drain_jobs()
        assert last_job_result("ingest").get("checks_job_id") is None

        # Lần sau: đổi cột trên file ĐÃ parsed → nối job chạy kiểm tra phạm vi hẹp.
        data["col_production_out_qty"] = str(int(base_map["production_out_qty"]) + 1)
        client.post(f"/companies/DN_JOB/documents/file/{fid}/review",
                    data=data, follow_redirects=False)
        with dbmod.SessionLocal() as db:
            assert db.query(Job).filter_by(kind="run_checks").count() == 0  # chưa xếp
        drain_jobs()

        res = last_job_result("ingest")
        assert res["checks_job_id"]
        with dbmod.SessionLocal() as db:
            follow = db.get(Job, res["checks_job_id"])
            last_ingest = db.query(Job).filter_by(kind="ingest").order_by(Job.id.desc()).first()
            assert follow.kind == "run_checks"
            assert follow.status == JobStatus.DONE.value
            assert follow.id > last_ingest.id  # xếp SAU khi nạp xong, không song song
    finally:
        _teardown(new_engine, prev_root)
