"""Hệ nhãn ba trục, hiện theo ngoại lệ (ADR #29, vé #119).

Trước đây template render VÔ ĐIỀU KIỆN hai nhãn mỗi trường, nên một file Mẫu 16 tám trường sạch
đeo 21 nhãn cùng lúc và hai nhãn xanh giống hệt nhau đứng cạnh nhau. Quy tắc mới: nhãn chỉ hiện
khi trạng thái KHÁC trường hợp mong đợi.

Khẳng định ở CẢ HAI đầu — bộ dựng ngữ cảnh và HTML — vì một khẳng định chỉ ở bộ dựng sẽ xanh trên
đúng template đang render thừa. Đọc `data-axis`, không dò câu chữ tiếng Việt trong HTML.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company
from app.pipeline.file_page import (
    AXES,
    AXIS_ASSIGNMENT,
    AXIS_WORK,
    file_page_url,
    file_read_basis,
)
from app.settings import settings
from tests.excel_fixtures import write_xlsx
from tests.test_file_page import REL_DIR, _register, _row


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_FP", name="Trang file", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)

_M16_FIELDS = (
    "product_code", "product_name", "product_unit", "material_code",
    "material_name", "material_unit", "norm_qty", "note",
)

# Mẫu 16 SẠCH: cả tám trường đã gán, bằng chứng khớp tiêu đề, không trường nào phải soát.
_M16_CLEAN = {
    "sheet": "BCQT_DM",
    "form_signature": "sig-m16",
    "column_map": {name: i for i, name in enumerate(_M16_FIELDS)},
    "columns": [
        {"field": name, "evidence": "header-matched", "review": "verified"}
        for name in _M16_FIELDS
    ],
}


def _seed_clean_m16(root, **kwargs) -> int:
    write_xlsx(root / REL_DIR / "m16.xlsx", [["Mã SP", 1]], sheet_name="BCQT_DM")
    return _register("m16.xlsx", slot="m16", parse_detail=_M16_CLEAN, **kwargs)


def _by_field(basis) -> dict:
    return {c.field: c for c in basis.columns}


def _badges(text: str) -> list[str]:
    """Mọi phần tử mang ĐÚNG lớp `badge` — `jobs-badge` là lớp khác, không tính."""
    return [
        tag
        for tag in re.findall(r"<span[^>]*>", text)
        if "badge" in re.sub(r'.*class="([^"]*)".*', r"\1", tag, flags=re.S).split()
    ]


def _axes_on_page(text: str) -> list[str]:
    return re.findall(r"data-axis=\"([a-z]+)\"", text)


def test_a_clean_assigned_field_carries_no_label(env):
    """Trường đã gán, bằng chứng đủ mạnh: bộ chọn cột đã nói hết, không nhãn nào thêm được gì."""
    _client, root = env
    fid = _seed_clean_m16(root)

    basis = file_read_basis(_row(fid))

    assert _by_field(basis)["product_code"].labels == ()


def test_an_absent_field_says_so_on_the_assignment_axis(env):
    _client, root = env
    fid = _seed_clean_m16(root)

    basis = file_read_basis(_row(fid), absent_fields=["note"])

    labels = _by_field(basis)["note"].labels
    assert [lb.axis for lb in labels] == [AXIS_ASSIGNMENT]


def test_an_unassigned_row_key_is_louder_than_an_unassigned_plain_field(env):
    """Thiếu khoá dòng thì không dựng nổi một dòng Tầng 1 nào — không cùng mức với trường thường."""
    _client, root = env
    detail = dict(_M16_CLEAN, column_map={}, columns=[])
    write_xlsx(root / REL_DIR / "m16.xlsx", [["Mã SP", 1]], sheet_name="BCQT_DM")
    fid = _register("m16.xlsx", slot="m16", parse_detail=detail)

    by_field = _by_field(file_read_basis(_row(fid)))

    row_key = by_field["product_code"].labels[0]
    plain = by_field["product_name"].labels[0]
    assert row_key.axis == plain.axis == AXIS_ASSIGNMENT
    assert row_key.tone != plain.tone


def test_a_field_still_to_confirm_carries_a_work_axis_label(env):
    _client, root = env
    detail = dict(
        _M16_CLEAN,
        columns=[
            {"field": "norm_qty", "evidence": "position-only", "review": "needs_review"},
        ],
    )
    write_xlsx(root / REL_DIR / "m16.xlsx", [["Mã SP", 1]], sheet_name="BCQT_DM")
    fid = _register("m16.xlsx", slot="m16", parse_detail=detail)

    labels = _by_field(file_read_basis(_row(fid)))["norm_qty"].labels

    assert [lb.axis for lb in labels] == [AXIS_WORK]


def test_no_check_reads_it_is_said_on_the_evidence_axis_not_by_a_label(env):
    """`review_state` trả `verified` cho trường không kiểm tra nào đọc — đó là chuyện của trục căn
    cứ, nên nó nằm trong câu căn cứ chứ không thành một nhãn riêng."""
    _client, root = env
    fid = _seed_clean_m16(root)

    by_field = _by_field(file_read_basis(_row(fid)))

    unread = by_field["product_name"]
    assert unread.checks == ()
    assert unread.labels == ()
    assert "kiểm tra" in unread.evidence_sentence.lower()


def test_every_label_declares_one_of_the_three_axes(env):
    _client, root = env
    fid = _seed_clean_m16(root)

    basis = file_read_basis(_row(fid), absent_fields=["note"])

    for column in basis.columns:
        for label in column.labels:
            assert label.axis in AXES


def test_a_clean_m16_page_renders_at_most_three_labels(env):
    """Số đo của vé: tám trường sạch hiện 21 nhãn trước khi sửa."""
    client, root = env
    fid = _seed_clean_m16(root)

    text = client.get(file_page_url("DN_FP", fid)).text

    assert len(_badges(text)) <= 3


def test_every_badge_on_the_file_page_declares_its_axis(env):
    client, root = env
    fid = _seed_clean_m16(root, match_source="officer")

    text = client.get(file_page_url("DN_FP", fid)).text

    for tag in _badges(text):
        assert "data-axis=" in tag, tag
    assert len(set(_axes_on_page(text))) <= 3


def test_the_checked_label_is_gone_from_the_product() -> None:
    """"Đã kiểm" cũng có nghĩa "không kiểm tra nào đọc trường này" — hai nghĩa trong một chuỗi."""
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    hits = [
        path
        for path in app_dir.rglob("*")
        if path.suffix in {".py", ".html"} and "Đã kiểm" in path.read_text(encoding="utf-8")
    ]
    assert hits == []
