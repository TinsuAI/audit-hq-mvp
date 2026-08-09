"""Đường xác nhận cột: quay về đâu, xếp việc gì, nói gì về lượt chạy kiểm tra (#125).

Nút chính trước vé này đọc là "Xác nhận & nạp dữ liệu" trên trang mang tên MỘT file,
trong khi lượt gửi nạp lại CẢ KỲ rồi bỏ cán bộ ở danh sách tài liệu, và không màn nào
nói rằng kiểm tra vẫn chưa chạy.

Đơn vị nạp KHÔNG đổi ở vé này — vẫn `(company_code, year)`. Thứ đổi là chỗ đứng xem
lượt nạp và những câu màn hình nói ra.
"""

from __future__ import annotations

from html import escape
from urllib.parse import unquote_plus

from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, CompanyYearScore, DataFile
from app.models.job import Job, JobKind
from app.pipeline.file_page import file_page_url
from tests.conftest import AppDb
from tests.helpers import (
    M15_HEADER,
    drain_jobs,
    m15_xlsx_bytes,
    unreadable_m15_xlsx_bytes,
    upload_and_ingest,
)

_CODE = "DN_CP"
_YEAR = 2024

# Cột 8 mang nhãn không khớp từ khoá → `production_out_qty` chỉ `balance-checked`,
# tức cổng xác nhận cột bật. Đó là điều kiện duy nhất fixture này cần khác biểu chuẩn.
_HEADER = [*M15_HEADER[:8], "Cột 8", *M15_HEADER[9:]]


def _client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=_CODE, name="Đường xác nhận", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client


def _awaiting_confirm(app_db: AppDb) -> tuple[TestClient, int, dict]:
    """DN có một file Mẫu 15 dừng ở cổng xác nhận cột; trả `(client, file_id, map)`."""
    client = _client(app_db)
    upload_and_ingest(client, _CODE, "Mau15_NVL.xlsx", m15_xlsx_bytes(_HEADER))
    drain_jobs()
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code=_CODE).one()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").one()
        return client, row.id, dict(row.parse_detail_obj["column_map"])


def _jobs(app_db: AppDb, kind: str) -> list[Job]:
    with app_db.SessionLocal() as db:
        return list(
            db.query(Job)
            .filter_by(kind=kind)
            .order_by(Job.id)
            .all()
        )


# ───────────────────── quay về trang file, không về danh sách ─────────────────────

def test_confirm_returns_to_the_file_page(app_db: AppDb):
    client, fid, base_map = _awaiting_confirm(app_db)

    r = client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == file_page_url(_CODE, fid)


def test_reingest_of_an_unreadable_file_also_returns_to_the_file_page(app_db: AppDb):
    """Nhánh KHÔNG có bố cục cột đi một đường thoát riêng — nó cũng phải về trang file."""
    client = _client(app_db)
    upload_and_ingest(client, _CODE, "Mau15_NVL.xlsx", unreadable_m15_xlsx_bytes(_HEADER))
    drain_jobs()
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code=_CODE).one()
        row = db.query(DataFile).filter_by(company_id=c.id).one()
        fid = row.id
        assert not row.parse_detail_obj.get("column_map")

    r = client.post(file_page_url(_CODE, fid), data={}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == file_page_url(_CODE, fid)


def test_a_rejected_column_index_returns_to_the_file_page_with_the_reason(app_db: AppDb):
    client, fid, base_map = _awaiting_confirm(app_db)
    data = {f"col_{f}": str(i) for f, i in base_map.items()}
    data["col_production_out_qty"] = "không phải số"

    r = client.post(file_page_url(_CODE, fid), data=data, follow_redirects=False)

    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith(f"{file_page_url(_CODE, fid)}?error=")
    reason = unquote_plus(location.split("?error=", 1)[1])
    # Câu từ chối do đường xác nhận dựng ra phải tới được màn — khẳng định trên đường
    # đi của chuỗi (query → khối cảnh báo), không dò một câu tiếng Việt viết sẵn.
    assert reason.strip()
    page = client.get(location).text
    assert 'class="form-alert form-alert-error"' in page
    assert escape(reason) in page


# ───────────────────── lần xác nhận đầu KHÔNG chạy kiểm tra ─────────────────────

def test_first_confirm_queues_an_ingest_and_no_check_run(app_db: AppDb):
    """Một kỳ có tới bốn file quyết toán; chạy trên bộ dữ liệu chưa đủ sẽ dựng lại
    `Finding` và đưa `status`/ghi chú của cán bộ về `new`. Khẳng định trên HÀNG ĐỢI."""
    client, fid, base_map = _awaiting_confirm(app_db)

    client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )

    queued = _jobs(app_db, JobKind.INGEST.value)[-1]
    assert "then_run_checks" not in queued.payload
    drain_jobs()
    assert _jobs(app_db, JobKind.RUN_CHECKS.value) == []


# ───────────────────── tiến độ lượt nạp in ngay trên trang file ─────────────────────

def test_file_page_prints_the_queued_ingest_and_polls_for_itself(app_db: AppDb):
    client, fid, base_map = _awaiting_confirm(app_db)
    client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )

    page = client.get(file_page_url(_CODE, fid)).text

    assert 'data-ingest-active="1"' in page
    assert f"/documents/ingest.json?year={_YEAR}&amp;file_id={fid}" in page
    assert "/static/ingest-poll.js" in page


def test_status_endpoint_reloads_the_file_page_when_the_file_page_asks(app_db: AppDb):
    client, fid, base_map = _awaiting_confirm(app_db)
    client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )
    drain_jobs()

    from_file = client.get(
        f"/companies/{_CODE}/documents/ingest.json?year={_YEAR}&file_id={fid}"
    ).json()
    from_period = client.get(
        f"/companies/{_CODE}/documents/ingest.json?year={_YEAR}"
    ).json()

    assert from_file["reload_url"].startswith(file_page_url(_CODE, fid))
    assert from_period["reload_url"].startswith(f"/companies/{_CODE}/documents?")


def test_status_endpoint_rejects_a_file_of_another_company(app_db: AppDb):
    client, fid, _ = _awaiting_confirm(app_db)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_KHAC", name="Khác", tax_id="2"))
        db.commit()

    r = client.get(f"/companies/DN_KHAC/documents/ingest.json?year={_YEAR}&file_id={fid}")

    assert r.status_code == 404


# ───────────────────── "kiểm tra chưa chạy" ở CẢ HAI màn ─────────────────────

def _confirm_and_ingest(app_db: AppDb) -> tuple[TestClient, int]:
    client, fid, base_map = _awaiting_confirm(app_db)
    client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )
    drain_jobs()
    return client, fid


# Câu chữ tiếng Việt KHÔNG khẳng định ở đây (quy ước repo, và AC 7 của vé ghi thẳng
# điều đó): test dò một chuỗi viết sẵn thì mọi lần biên tập câu là một lần đỏ giả. Vế
# hành vi khẳng định qua `data-checks-run` và qua biểu mẫu chạy nằm trong khối đó; vế
# câu chữ do người soát.

def test_file_page_flags_the_unrun_checks_and_puts_the_action_beside_it(app_db: AppDb):
    client, fid = _confirm_and_ingest(app_db)

    page = client.get(file_page_url(_CODE, fid)).text

    assert 'data-checks-run="0"' in page
    block = page.split('class="fp-checks"', 1)[1].split("</div>", 1)[0]
    assert f'action="/companies/{_CODE}/run-checks"' in block


def test_period_row_flags_the_unrun_checks_beside_its_own_run_button(app_db: AppDb):
    client, _ = _confirm_and_ingest(app_db)

    page = client.get(f"/companies/{_CODE}/documents").text

    block = page.split('class="ds-run-checks" data-checks-run="0"', 1)[1]
    block = block.split("</div>", 1)[0]
    assert f'action="/companies/{_CODE}/run-checks"' in block
    # Một nút cho một việc: câu thêm vào, nút không nhân đôi.
    assert page.count(f'action="/companies/{_CODE}/run-checks"') == 1


def test_both_screens_go_quiet_once_the_checks_have_run(app_db: AppDb):
    client, fid = _confirm_and_ingest(app_db)
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code=_CODE).one()
        db.add(CompanyYearScore(
            company_id=c.id, period_year=_YEAR, score=12,
            tier="Có chênh lệch nhỏ", breakdown={},
        ))
        db.commit()

    file_page = client.get(file_page_url(_CODE, fid)).text
    period_page = client.get(f"/companies/{_CODE}/documents").text

    assert 'class="fp-checks"' not in file_page
    assert 'data-checks-run="1"' in period_page
    assert 'data-checks-run="0"' not in period_page


# ───────────────────── nhãn nút ─────────────────────

def test_the_primary_button_carries_no_emoji(app_db: AppDb):
    """Vế DUY NHẤT của nhãn nút khẳng định được mà không dò câu chữ: không emoji.

    Phạm vi nhãn nêu ra (vị trí cột + nạp lại dữ liệu của kỳ) là việc người soát —
    khẳng định nó bằng chuỗi tiếng Việt là buộc mọi lần biên tập câu phải sửa test.
    """
    client, fid, _ = _awaiting_confirm(app_db)

    page = client.get(file_page_url(_CODE, fid)).text

    label = page.split('class="btn btn-primary">', 1)[1].split("<", 1)[0]
    assert not [ch for ch in label if ord(ch) > 0x2100], label


def test_the_ingest_unit_is_still_the_period(app_db: AppDb):
    """Nút đổi chữ, KHÔNG đổi việc: job vẫn mang `(company_code, year)`, không mang file."""
    client, fid, base_map = _awaiting_confirm(app_db)

    client.post(
        file_page_url(_CODE, fid),
        data={f"col_{f}": str(i) for f, i in base_map.items()},
        follow_redirects=False,
    )

    payload = _jobs(app_db, JobKind.INGEST.value)[-1].payload
    assert payload["company_code"] == _CODE
    assert payload["year"] == _YEAR
    assert "file_id" not in payload
