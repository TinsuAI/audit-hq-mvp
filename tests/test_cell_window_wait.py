"""Trạng thái ĐANG TRÍCH XUẤT — request không được treo tới lúc bị cắt.

Số đo ở #83: lượt trích xuất đầu của file `.xlsx` 71,3MB mất 164,6 giây, vượt
ngưỡng cắt 100 giây của Cloudflare. Lượt dựng vẫn chạy tiếp sau khi máy khách rớt
và vào chỗ bằng đổi tên nguyên tử, nên vấn đề còn lại là GIAO DIỆN: điểm cuối phải
chờ có hạn rồi trả 202 kèm tiến trình để lưới tự hỏi lại, thay vì giữ kết nối.

Khẳng định ở mức JSON, không dò chuỗi tiếng Việt trong HTML.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters import cell_window
from app.adapters.cell_reader import CellReadError, SheetRow
from app.main import app
from app.models import Company, DataFile
from app.settings import settings
from tests.excel_fixtures import write_xlsx

REL_DIR = "DN_PV/2025/HANG_CHI_TIET"


class _GatedReader:
    """Bộ đọc giả chặn giữa chừng ở một `Event` — cho test giữ lượt trích xuất đang chạy.

    Chạy trên file lớn thật thì thời điểm 202 phụ thuộc tốc độ máy; cổng chặn làm
    ranh giới "chưa xong / đã xong" thành thứ test điều khiển được.
    """

    fmt = "xlsx"
    format_label = "Bảng tính Excel dạng gói ZIP (OOXML)"
    formulas_supported = True
    formula_note = None

    def __init__(self, gate: threading.Event, rows_before: int = 4000, fail: bool = False) -> None:
        self.gate = gate
        self.rows_before = rows_before
        self.fail = fail

    def sheet_names(self) -> list[str]:
        return ["Chi tiết"]

    def iter_sheet_rows(self, sheet_index: int):
        for r in range(self.rows_before):
            yield SheetRow(r, [f"r{r}", r], {})
        self.gate.wait(30)
        if self.fail:
            raise CellReadError("Trang tính hỏng giữa chừng.")
        yield SheetRow(self.rows_before, ["dòng cuối", 1], {})


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    """Client đã đăng nhập + một DN + kho đệm xem trước trong thư mục tạm."""
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    cell_window.reset_build_locks()
    cell_window.reset_extract_jobs()
    (tmp_path / REL_DIR).mkdir(parents=True, exist_ok=True)

    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_PV", name="PV", tax_id="1"))
        db.commit()

    gates: list[threading.Event] = []
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    try:
        yield client, tmp_path, gates
    finally:
        for g in gates:
            g.set()
        cell_window.reset_extract_jobs()


def _register(name: str) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_PV").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="bcct",
            original_filename=name, stored_path=rel,
            size_bytes=(Path(settings.raw_data_path) / rel).stat().st_size,
            parse_status="ok", row_count=1,
        )
        db.add(row)
        db.commit()
        return row.id


def _gated_file(env, *, fail: bool = False) -> tuple[int, threading.Event]:
    """File thật trên đĩa (để dò định dạng) + bộ đọc giả bị chặn ở cổng."""
    client, tmp_path, gates = env
    path = tmp_path / REL_DIR / "cham.xlsx"
    write_xlsx(path, [["Mã", "SL"], ["A1", 1]])
    fid = _register("cham.xlsx")

    gate = threading.Event()
    gates.append(gate)
    reader = _GatedReader(gate, fail=fail)
    cell_window.open_reader = lambda p, _r=reader: _r  # type: ignore[assignment]
    return fid, gate


@pytest.fixture(autouse=True)
def _restore_open_reader():
    original = cell_window.open_reader
    yield
    cell_window.open_reader = original


def _url(fid: int, **params) -> str:
    from urllib.parse import urlencode

    return f"/companies/DN_PV/documents/file/{fid}/cells?{urlencode(params)}"


def _poll(client, fid, *, until, timeout_s: float = 20.0, **params):
    """Hỏi lại như lưới hỏi: `wait=0`, cách nhau chút, tới khi điều kiện đúng."""
    deadline = time.monotonic() + timeout_s
    last = client.get(_url(fid, wait=0, **params))
    while not until(last) and time.monotonic() < deadline:
        time.sleep(0.05)
        last = client.get(_url(fid, wait=0, **params))
    return last


def test_a_cold_open_reports_the_extracting_state_instead_of_holding_the_request(env):
    client, _, _ = env
    fid, _gate = _gated_file(env)

    r = client.get(_url(fid, wait=0))

    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "extracting"
    # Cán bộ phải biết đây là lần đầu mở file này và lần sau sẽ tức thì.
    assert body["first_open"] is True
    assert body["rows_done"] >= 0
    assert body["elapsed_ms"] >= 0


def test_the_extracting_state_carries_progress_that_moves(env):
    client, _, _ = env
    fid, _gate = _gated_file(env)

    r = _poll(client, fid, until=lambda r: r.json().get("rows_done", 0) >= 2000)

    assert r.status_code == 202
    assert r.json()["rows_done"] >= 2000


def test_the_window_arrives_on_a_later_poll_without_the_officer_asking_again(env):
    client, _, _ = env
    fid, gate = _gated_file(env)

    assert client.get(_url(fid, wait=0)).status_code == 202
    gate.set()
    r = _poll(client, fid, until=lambda r: r.status_code == 200, rows=3, row=4000)

    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 4001
    assert body["rows"][0] == ["dòng cuối", 1]


def test_a_warm_cache_serves_the_window_with_no_wait_budget_at_all(env):
    client, _, _ = env
    fid, gate = _gated_file(env)
    gate.set()
    _poll(client, fid, until=lambda r: r.status_code == 200)

    r = client.get(_url(fid, wait=0))

    assert r.status_code == 200
    assert r.json()["from_cache"] is True


def test_a_file_the_reader_cannot_open_fails_at_once_not_after_the_wait(env):
    client, tmp_path, _ = env
    path = tmp_path / REL_DIR / "gia.xlsx"
    path.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    fid = _register("gia.xlsx")

    started = time.monotonic()
    r = client.get(_url(fid, wait=0))

    assert r.status_code == 415
    assert time.monotonic() - started < 5
    assert "PDF" in r.json()["detail"]


def test_a_read_error_hit_after_the_first_202_comes_back_as_a_terminal_error(env):
    client, _, _ = env
    fid, gate = _gated_file(env, fail=True)

    assert client.get(_url(fid, wait=0)).status_code == 202
    gate.set()
    r = _poll(client, fid, until=lambda r: r.status_code != 202)

    assert r.status_code == 422
    assert r.json()["detail"]


def test_a_finished_job_is_not_called_ready_once_its_cache_file_is_gone(env):
    """Kho đệm bị dọn sau khi dựng xong: "xong" phải theo KHO, không theo việc.

    Nhận là xong lúc kho đã mất thì người gọi đọc hụt rồi lùi về dựng đồng bộ
    ngay trong request — đo được 46,5 giây trên file 200.000 dòng, và 164,6 giây
    trên file 71,3 MB thì vượt hẳn biên cắt 100 giây.
    """
    client, tmp_path, _ = env
    fid, gate = _gated_file(env)

    assert client.get(_url(fid, wait=0)).status_code == 202  # việc vào sổ, chưa xong
    gate.set()
    src = Path(settings.raw_data_path) / REL_DIR / "cham.xlsx"
    dest = cell_window.cache_file_for(src, 0)
    deadline = time.monotonic() + 20
    while not dest.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert dest.exists()
    dest.unlink()  # việc VẪN nằm trong sổ, chưa ai đọc kết quả

    status = cell_window.request_extract(src, 0, wait_s=0)

    assert status.ready is False


def test_a_wiped_cache_makes_the_endpoint_wait_again_instead_of_rebuilding_inline(env):
    client, tmp_path, gates = env
    fid, gate = _gated_file(env)
    gate.set()
    _poll(client, fid, until=lambda r: r.status_code == 200)
    for f in (tmp_path / "kho-dem").glob("*.sqlite"):
        f.unlink()
    # Lượt dựng mới KHÔNG thể xong (cổng đóng): request nào dựng đồng bộ sẽ treo.
    stuck = threading.Event()
    gates.append(stuck)
    stuck_reader = _GatedReader(stuck)
    cell_window.open_reader = lambda p, _r=stuck_reader: _r

    started = time.monotonic()
    r = client.get(_url(fid, wait=0))

    assert r.status_code == 202
    assert time.monotonic() - started < 5


def test_a_file_that_extracts_quickly_needs_only_one_request(env):
    client, tmp_path, _ = env
    path = tmp_path / REL_DIR / "nho.xlsx"
    write_xlsx(path, [[f"r{r}c{c}" for c in range(6)] for r in range(400)])
    fid = _register("nho.xlsx")

    r = client.get(_url(fid))

    assert r.status_code == 200
    assert r.json()["total_rows"] == 400
