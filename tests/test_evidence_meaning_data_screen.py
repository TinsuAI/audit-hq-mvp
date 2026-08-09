"""Nghĩa của nguồn bằng chứng ở MÀN DỮ LIỆU, thành chữ chứ không thành tooltip (#130).

#120 đóng phần trang file: mỗi dòng trường mang câu nêu cơ chế và giới hạn của nó. Màn
dữ liệu thì chưa — nó vẫn in `evidence_label` trần trong một chip, và nghĩa chỉ nằm ở
thuộc tính `title`. Tooltip không hiện trên thiết bị cảm ứng, không hiện khi in, và không
đọc được bằng bàn phím nếu không rê chuột được.

Ràng buộc đi kèm, và cả hai đều được khẳng định ở đây: chip GIỮ nhãn ngắn (nhãn đó đi vào
`parse_detail` lúc nạp, đổi nó là làm file cũ và file mới hiện hai kiểu), và file nạp
TRƯỚC #120 — bản `parse_detail` không chứa câu nào — vẫn đọc được nghĩa.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.adapters.evidence import (
    BALANCE_CHECKED,
    HEADER_MATCHED,
    OFFICER_CONFIRMED,
    POSITION_ONLY,
    SOURCE_LABEL_VI,
    SOURCE_SENTENCE_VI,
    source_meanings,
)
from app.main import app
from app.models import Company, DataFile, NvlBalance
from tests.conftest import AppDb

_CODE = "DN_EV"
_YEAR = 2025

#: Bản `parse_detail` như file nạp TRƯỚC #120 để lại: nhãn ngắn, KHÔNG câu nào.
_LEGACY_DETAIL = {
    "sheet": "BCQT_NVL",
    "columns": [
        {"field": "material_code", "label": "Mã NVL",
         "evidence": HEADER_MATCHED, "evidence_label": SOURCE_LABEL_VI[HEADER_MATCHED],
         "review": "verified"},
        {"field": "production_out_qty", "label": "Xuất sản xuất",
         "evidence": POSITION_ONLY, "evidence_label": SOURCE_LABEL_VI[POSITION_ONLY],
         "review": "needs_review"},
        {"field": "closing_qty", "label": "Tồn cuối kỳ",
         "evidence": BALANCE_CHECKED, "evidence_label": SOURCE_LABEL_VI[BALANCE_CHECKED],
         "review": "needs_review"},
    ],
}


@pytest.fixture
def client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=_CODE, name="Bằng chứng", tax_id="1"))
        db.commit()
        company = db.query(Company).filter_by(code=_CODE).one()
        db.add(DataFile(
            company_id=company.id, period_year=_YEAR, slot="m15",
            original_filename="m15.xlsx", stored_path=f"{_CODE}/{_YEAR}/BCQT/m15.xlsx",
            size_bytes=1, parse_status="parsed", row_count=1, parse_layout="standard",
            parse_detail=json.dumps(_LEGACY_DETAIL, ensure_ascii=False),
        ))
        db.add(NvlBalance(
            company_id=company.id, period_year=_YEAR, material_code="MAT0",
            material_name="Tên", unit="KG", opening_qty=10, import_qty=100,
            reexport_qty=0, repurpose_qty=0, production_out_qty=80, other_out_qty=0,
            closing_qty=30,
        ))
        db.commit()
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return c


def _page(client: TestClient) -> str:
    return client.get(f"/companies/{_CODE}/data?year={_YEAR}&table=m15").text


def _key_block(html: str) -> str:
    return html.split('<dl class="evidence-key">', 1)[1].split("</dl>", 1)[0]


# ─────────────── nghĩa hiện thành chữ, không phụ thuộc rê chuột ───────────────

def test_every_source_on_screen_has_its_meaning_as_visible_text(client: TestClient):
    html = _page(client)
    block = _key_block(html)

    for source in (HEADER_MATCHED, POSITION_ONLY, BALANCE_CHECKED):
        assert SOURCE_LABEL_VI[source] in block
        assert SOURCE_SENTENCE_VI[source] in block


def test_the_meaning_does_not_live_in_a_tooltip(client: TestClient):
    """Không thuộc tính `title` nào mang câu nghĩa — chữ phải đọc được mà không rê chuột."""
    html = _page(client)

    titles = re.findall(r'title="([^"]*)"', html)
    for sentence in SOURCE_SENTENCE_VI.values():
        assert not any(sentence in t for t in titles), sentence


def test_the_yellow_badge_says_what_it_means(client: TestClient):
    """Cặp `Đã gán`/`Chưa gán` ở màn này chỉ còn là SẮC THÁI của chip; nói ra bằng chữ."""
    block = _key_block(_page(client))

    assert "nhãn nền vàng" in block.lower()
    assert "xác nhận vị trí cột" in block


# ─────────────── chip giữ chữ ngắn ───────────────

def test_the_chip_keeps_the_short_label(client: TestClient):
    html = _page(client)
    chips = html.split('<div class="evidence-cols">', 1)[1].split("</div>", 1)[0]

    for source in (HEADER_MATCHED, POSITION_ONLY, BALANCE_CHECKED):
        assert SOURCE_LABEL_VI[source] in chips
        assert SOURCE_SENTENCE_VI[source] not in chips


def test_no_new_badge_axis_appears(client: TestClient):
    """ADR #29: nhãn chỉ thuộc ba trục đã khai. Khối nghĩa KHÔNG được thêm chip nào."""
    block = _key_block(_page(client))

    assert "badge" not in block
    assert "data-axis" not in block


# ─────────────── file nạp trước #120 ───────────────

def test_a_file_stored_before_the_sentences_existed_still_reads(client: TestClient):
    """`parse_detail` của fixture không chứa câu nào — nghĩa phải tra được lúc render."""
    stored = json.dumps(_LEGACY_DETAIL, ensure_ascii=False)
    for sentence in SOURCE_SENTENCE_VI.values():
        assert sentence not in stored

    block = _key_block(_page(client))
    assert SOURCE_SENTENCE_VI[POSITION_ONLY] in block


# ─────────────── bộ dựng, không qua HTTP ───────────────

def test_source_meanings_lists_each_source_once_weakest_first():
    columns = [
        {"evidence": HEADER_MATCHED},
        {"evidence": POSITION_ONLY},
        {"evidence": HEADER_MATCHED},
        {"evidence": OFFICER_CONFIRMED},
    ]

    got = source_meanings(columns)

    assert [m.source for m in got] == [POSITION_ONLY, HEADER_MATCHED, OFFICER_CONFIRMED]
    assert [m.weak for m in got] == [True, False, False]


def test_source_meanings_survives_a_column_with_no_evidence():
    assert source_meanings([{"field": "x"}, None, {"evidence": ""}]) == ()
    assert source_meanings(None) == ()
