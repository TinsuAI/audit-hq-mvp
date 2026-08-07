"""Nạp dữ liệu chạy ở hàng đợi, không trong request (job `ingest`).

Cloudflare cắt kết nối ở 100 giây, mà một lượt tải lên đọc file mất vài phút với
bộ dữ liệu thật (BCCT 68MB của 006: 97 giây một lượt đọc, ba lượt một lần tải).
Test giữ: request chỉ lưu file rồi xếp job; job chạy mới sinh dòng; và mọi kết
luận của job (chẩn đoán lỗi, dừng chờ xác nhận, kế hoạch sổ sai) đều có nhãn để
hiện lên trang công việc thay vì biến mất cùng redirect.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.jobs.result_labels import RESULT_LABEL_VI
from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.models.job import Job, JobStatus
from tests.conftest import AppDb
from tests.helpers import (
    M15_HEADER,
    XLSX_MIME,
    drain_jobs,
    last_job_result,
    m15_xlsx_bytes,
    upload_and_ingest,
)

# Cột 8 nhãn không khớp từ khoá → `production_out_qty` chỉ balance-checked → needs_review.
_M15_HEADER_NEEDS_REVIEW = [*M15_HEADER[:8], "Cột 8", *M15_HEADER[9:]]


def _client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_JOB", name="Job", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client


def _upload(client, content: bytes, code: str = "DN_JOB", year: int = 2024):
    return upload_and_ingest(client, code, "Mau15_NVL.xlsx", content, year)


def _not_m15_bytes() -> bytes:
    wb = Workbook()
    wb.active.append(["không", "phải", "mẫu", "15"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _labels_ok(result: dict) -> bool:
    return set(result) <= set(RESULT_LABEL_VI)


def test_dropping_a_file_queues_nothing(app_db: AppDb):
    """Ô thả chỉ lưu file (#88) — cán bộ còn sửa loại và gán sổ trước khi nạp."""
    client = _client(app_db)
    r = client.post(
        "/companies/DN_JOB/upload",
        data={"year": "2024"},
        files=[("files", ("Mau15_NVL.xlsx", m15_xlsx_bytes(), XLSX_MIME))],
        follow_redirects=False,
    )
    assert r.status_code == 303
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        assert db.query(Job).count() == 0
        assert db.query(DataFile).filter_by(company_id=c.id, slot="m15").count() == 1


def test_ingest_request_only_queues_a_job(app_db: AppDb):
    """Request KHÔNG đọc file: file đã lưu + job queued, chưa dòng nào vào DB."""
    client = _client(app_db)
    r = _upload(client, m15_xlsx_bytes())

    assert r.status_code == 303
    # Cán bộ ở lại màn dữ liệu, đúng dòng kỳ vừa xếp lượt nạp (#89).
    assert r.headers["location"].endswith("/documents#ky-2024")

    with app_db.SessionLocal() as db:
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
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 3


def test_job_result_reports_rows_and_has_labels(app_db: AppDb):
    client = _client(app_db)
    _upload(client, m15_xlsx_bytes())
    drain_jobs()

    res = last_job_result("ingest")
    assert res["status"] == "ok"
    assert res["m15_rows"] == 3
    assert res["bcct_rows"] == 0
    assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"


def test_unreadable_file_reports_diagnosis_on_the_job(app_db: AppDb):
    """File sai mẫu: job DONE kèm danh sách chẩn đoán (trước đây là trang 422)."""
    client = _client(app_db)
    # Workbook hợp lệ nhưng không có biểu Mẫu 15 nào → chẩn đoán báo lỗi.
    _upload(client, _not_m15_bytes())
    drain_jobs()

    res = last_job_result("ingest")
    assert res["status"] == "diagnosis_error"
    assert res["diagnostics"], "phải nêu được lỗi cụ thể cho cán bộ"
    assert {"slot", "level", "title", "detail"} <= set(res["diagnostics"][0])
    assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0


def test_period_row_shows_the_queued_state_and_starts_polling(app_db: AppDb):
    """Bấm nạp xong, dòng kỳ nói ĐANG CHỜ và tự hỏi lại.

    `TestClient(app)` không vào context manager nên không có worker — job đứng ở
    `queued`, đúng trạng thái cần nhìn thấy.
    """
    client = _client(app_db)
    _upload(client, m15_xlsx_bytes())

    html = client.get("/companies/DN_JOB/documents").text
    assert "Đang chờ trong hàng đợi" in html
    assert 'data-ingest-active="1"' in html
    assert "/static/ingest-poll.js" in html


def test_period_row_renders_the_diagnosis(app_db: AppDb):
    """Chẩn đoán đọc được NGAY TẠI DÒNG KỲ, cạnh nút xử lý (#89).

    Trước đây nó nằm ở trang 422, rồi ở trang công việc — cả hai đều bắt cán bộ
    rời màn dữ liệu để đọc một câu về chính kỳ họ đang làm.
    """
    client = _client(app_db)
    _upload(client, _not_m15_bytes())
    drain_jobs()

    html = client.get("/companies/DN_JOB/documents").text
    assert "hệ thống đọc không ra file" in html
    assert "không chọn được sheet đúng biểu" in html   # tiêu đề chẩn đoán cụ thể
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        fid = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first().id
    # Nút chọn trang tính nằm ngay đó, không phải một câu bảo sang trang khác.
    assert f"/documents/file/{fid}/review" in html


def test_gate_stops_before_writing_rows(app_db: AppDb):
    client = _client(app_db)
    _upload(client, m15_xlsx_bytes(_M15_HEADER_NEEDS_REVIEW))
    drain_jobs()

    res = last_job_result("ingest")
    assert res["status"] == "needs_review"
    assert res["review_columns"], "phải nêu cột nào cần xác nhận"
    assert _labels_ok(res), f"khoá chưa có nhãn: {set(res) - set(RESULT_LABEL_VI)}"

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ANALYZED
        assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0


def test_the_ingest_button_keeps_stopping_until_the_columns_are_confirmed(app_db: AppDb):
    """Nút nạp chạy với `gate=True` (#88): sau khi ô thả thôi xếp việc, đây là đường
    nạp DUY NHẤT trên web — bỏ cổng ở đây là để cấu trúc chưa ai xác nhận ghi thẳng
    dòng bằng cột đoán được. Bấm lại mà chưa xác nhận cột thì vẫn dừng, không ghi dòng.
    """
    client = _client(app_db)
    _upload(client, m15_xlsx_bytes(_M15_HEADER_NEEDS_REVIEW))
    drain_jobs()
    assert last_job_result("ingest")["status"] == "needs_review"

    r = client.post(
        "/companies/DN_JOB/documents/ingest", data={"year": "2024"}, follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/documents#ky-2024")
    with app_db.SessionLocal() as db:
        job = db.query(Job).order_by(Job.id.desc()).first()
        assert job.payload["gate"] is True
    drain_jobs()

    assert last_job_result("ingest")["status"] == "needs_review"
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        assert db.query(NvlBalance).filter_by(company_id=c.id).count() == 0


def test_failed_ingest_does_not_chain_check_job(app_db: AppDb):
    """Nạp hỏng thì KHÔNG nối job kiểm tra — chạy kiểm tra trên dữ liệu cũ là sai lệch."""
    from app.jobs.handlers import ingest_handler

    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_JOB", name="Job", tax_id="1"))
        db.commit()

    bcqt = app_db.raw_root / "DN_JOB" / "2024" / "BCQT"
    bcqt.mkdir(parents=True, exist_ok=True)
    (bcqt / "M15_NVL_2024.xlsx").write_bytes(_not_m15_bytes())

    with app_db.SessionLocal() as db:
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


def test_confirm_review_chains_a_check_job_after_ingest(app_db: AppDb):
    """Sửa cột trên file đã parsed: job nạp chạy trước, job kiểm tra do nó xếp ra sau."""
    client = _client(app_db)
    _upload(client, m15_xlsx_bytes(_M15_HEADER_NEEDS_REVIEW))
    drain_jobs()

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_JOB").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        fid, base_map = row.id, dict(row.parse_detail_obj["column_map"])

    # Lần confirm đầu (analyzed→parsed): chưa có finding nên KHÔNG nối job kiểm tra.
    data = {f"col_{f}": str(i) for f, i in base_map.items()}
    client.post(f"/companies/DN_JOB/documents/file/{fid}/review",
                data=data, follow_redirects=False)
    drain_jobs()
    assert last_job_result("ingest").get("checks_job_id") is None

    # Lần sau: đổi cột trên file ĐÃ parsed → nối job chạy kiểm tra phạm vi hẹp. Dời sang
    # cột PHỤ ngoài biểu (#95: biểu mẫu từ chối gán một cột cho hai trường, nên không
    # dời sang cột `Xuất khác` được nữa).
    data["col_production_out_qty"] = str(len(_M15_HEADER_NEEDS_REVIEW))
    client.post(f"/companies/DN_JOB/documents/file/{fid}/review",
                data=data, follow_redirects=False)
    with app_db.SessionLocal() as db:
        assert db.query(Job).filter_by(kind="run_checks").count() == 0  # chưa xếp
    drain_jobs()

    res = last_job_result("ingest")
    assert res["checks_job_id"]
    with app_db.SessionLocal() as db:
        follow = db.get(Job, res["checks_job_id"])
        last_ingest = db.query(Job).filter_by(kind="ingest").order_by(Job.id.desc()).first()
        assert follow.kind == "run_checks"
        assert follow.status == JobStatus.DONE.value
        assert follow.id > last_ingest.id  # xếp SAU khi nạp xong, không song song
