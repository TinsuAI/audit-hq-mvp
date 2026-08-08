"""Trục căn cứ nói bằng CÂU tại chỗ dùng, và thẻ tổng hợp "Căn cứ đọc file" biến mất (#120).

Hai điều khác nhau bị gộp làm một ở bản cũ. `SOURCE_LABEL_VI` là nhãn NGẮN đi vào chip và
đi vào `parse_detail` lúc nạp — đổi nó là đổi cả dữ liệu đã lưu của file nạp trước. Còn cái
cán bộ cần đọc ở dòng của trường là một CÂU nêu cơ chế VÀ giới hạn của cơ chế đó. Nên câu
nằm ở hằng riêng (`SOURCE_SENTENCE_VI`), tra lúc render, không ghi xuống DB.

Thẻ "Căn cứ đọc file" khẳng định đã xoá bằng HÌNH DẠNG DỮ LIỆU (trường nào còn trên
`ReadBasis`), không bằng sự vắng mặt của một chuỗi HTML — chuỗi vắng mặt vì đổi câu chữ
cũng làm test xanh, mà trường vẫn còn thì lần sau ai đó dựng lại thẻ.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.evidence import (
    _RANK,
    BALANCE_CHECKED,
    SOURCE_LABEL_VI,
    SOURCE_SENTENCE_VI,
)
from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import (
    ABSENT,
    ASSIGNED,
    UNASSIGNED,
    BasisColumn,
    ReadBasis,
    file_page_url,
)
from app.settings import settings
from tests.excel_fixtures import write_xlsx

REL_DIR = "DN_EP/2025/BCQT"

_DETAIL = {
    "sheet": "BCQT_NVL",
    "form_signature": "sig-m15",
    "column_map": {"material_code": 1, "production_out_qty": 8},
    "columns": [
        {"field": "material_code", "label": "Mã NVL",
         "evidence": "header-matched", "review": "verified"},
        {"field": "production_out_qty", "label": "Xuất sản xuất",
         "evidence": "balance-checked", "review": "needs_review"},
    ],
}


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_EP", name="Câu căn cứ", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _register(*, parse_detail: dict | None = None, row_count: int | None = 3) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/m15.xlsx"
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EP").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="m15",
            original_filename="m15.xlsx", stored_path=rel,
            size_bytes=(Path(settings.raw_data_path) / rel).stat().st_size,
            parse_status="parsed", row_count=row_count,
            parse_detail=json.dumps(parse_detail, ensure_ascii=False) if parse_detail else None,
        )
        db.add(row)
        db.commit()
        return row.id


def _register_for_data_screen() -> None:
    """File m15 bố cục chuẩn kèm cột bằng chứng ĐÃ LƯU — đúng hình dạng màn dữ liệu đọc.

    Cột bằng chứng dựng qua chính `_evidence_columns` của đường nạp, nên bản lưu ở đây
    giống bản một lượt nạp thật ghi ra: chỉ có nhãn NGẮN, không có câu nào.
    """
    import app.database as dbmod
    from app.adapters.evidence import HEADER_MATCHED, NEEDS_REVIEW, POSITION_ONLY
    from app.pipeline.data_files import _evidence_columns

    ev = {
        "material_code": HEADER_MATCHED, "opening_qty": HEADER_MATCHED,
        "production_out_qty": POSITION_ONLY, "closing_qty": HEADER_MATCHED,
    }
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_EP").one()
        db.add(DataFile(
            company_id=c.id, period_year=2025, slot="m15",
            original_filename="NVL.xlsx", stored_path=f"{REL_DIR}/m15.xlsx", size_bytes=1,
            parse_status="ok", row_count=1, parse_layout="standard",
            parse_detail=json.dumps(
                {"columns": _evidence_columns("m15", ev), "review": NEEDS_REVIEW},
                ensure_ascii=False,
            ),
        ))
        db.commit()


def _col(**kw) -> BasisColumn:
    base = dict(
        field="production_out_qty", label="Xuất sản xuất", evidence=BALANCE_CHECKED,
        evidence_label=SOURCE_LABEL_VI[BALANCE_CHECKED], review="verified",
        needs_review=False, columns=(8,), column_ref="I", checks=("C4.3",),
    )
    return BasisColumn(**{**base, **kw})


# ─────────────────────── câu căn cứ: cơ chế VÀ giới hạn ───────────────────────

def test_every_evidence_source_has_a_sentence():
    """Năm nguồn, năm câu. Thiếu một nguồn là một dòng trường không giải thích được."""
    assert set(SOURCE_SENTENCE_VI) == set(_RANK)


def test_each_sentence_states_a_limit_not_just_a_mechanism():
    """Nêu mỗi cơ chế thì cán bộ vẫn không biết khi nào KHÔNG tin được.

    Đo bằng hình dạng: câu phải có dấu ngắt mệnh đề (`;` hoặc `—`) tách phần cơ chế khỏi
    phần giới hạn, và phải dài hơn hẳn nhãn chip cùng khoá — nhãn chip là thuật ngữ trần,
    đúng thứ vé này thay.
    """
    for source, sentence in SOURCE_SENTENCE_VI.items():
        assert ";" in sentence or "—" in sentence, f"{source}: câu không tách phần giới hạn"
        assert len(sentence) > len(SOURCE_LABEL_VI[source]) * 3, f"{source}: chưa thành câu"
        assert sentence.endswith("."), f"{source}: câu không kết thúc bằng dấu chấm"


def test_the_balance_sentence_names_the_two_same_sign_columns_limit():
    """Giới hạn ĐÃ BIẾT của đẳng thức cân đối, nêu ở docstring `evidence.py` từ WS1.

    Đây là giới hạn khiến cột `balance-checked` vẫn phải cán bộ xác nhận: đẳng thức khớp
    không chứng minh được đang lấy đúng cột trong hai cột cùng dấu.
    """
    assert "cùng dấu" in SOURCE_SENTENCE_VI[BALANCE_CHECKED]


def test_the_short_chip_labels_are_left_alone():
    """Nhãn ngắn ĐI VÀO `parse_detail` lúc nạp (`data_files.py`), nên đổi là đổi dữ liệu đã lưu.

    File nạp trước giữ chuỗi cũ trong DB còn file nạp sau mang chuỗi mới → màn dữ liệu ra
    kết quả lẫn lộn. Câu mới sống ở hằng riêng, tra lúc render, chính vì vậy.
    """
    assert SOURCE_LABEL_VI[BALANCE_CHECKED] == "Khớp đẳng thức"
    assert set(SOURCE_LABEL_VI) == set(SOURCE_SENTENCE_VI)


# ─────────────────────── câu hiện ở dòng của trường ───────────────────────

def test_an_assigned_column_reads_the_term_followed_by_its_meaning():
    """Thuật ngữ đứng trước nghĩa, KHÔNG bị nghĩa thay thế.

    Xoá hẳn thuật ngữ khỏi trang file thì mục B7 cẩm nang (liên kết ở dòng trạng thái)
    định nghĩa một bộ từ vựng không khớp thứ gì trên màn hình, mà chip ở màn dữ liệu vẫn
    hiện đúng những chữ đó. AC 6 đòi thuật ngữ CÓ NGHĨA CẠNH NÓ, không đòi xoá thuật ngữ.
    """
    sentence = _col().evidence_sentence

    assert sentence.startswith(SOURCE_LABEL_VI[BALANCE_CHECKED])
    assert SOURCE_SENTENCE_VI[BALANCE_CHECKED] in sentence


def test_a_column_no_check_reads_says_so_after_the_sentence():
    """`review_state` trả `verified` cho ca này, nên nhãn dựng từ `review` nói sai."""
    sentence = _col(checks=()).evidence_sentence
    assert SOURCE_SENTENCE_VI[BALANCE_CHECKED] in sentence
    assert "Không kiểm tra nào đọc trường này" in sentence


def test_an_unassigned_column_explains_what_unassigned_means():
    """Nửa sau của cặp AC 6: nhãn "Chưa gán" render trần, không câu nào cạnh nó.

    Câu phải nói cả NGHĨA (hệ thống không đọc gì) lẫn THAO TÁC (chọn cột, hoặc khai vắng).
    Nhãn chỉ nêu trạng thái thì cán bộ đọc xong vẫn không biết phải bấm gì.
    """
    sentence = _col(state=UNASSIGNED, columns=(), column_ref="", evidence=None,
                    evidence_label="").evidence_sentence

    assert "không đọc" in sentence.lower()
    assert "Không có trong file" in sentence


def test_an_absent_column_says_the_officer_decided_it():
    sentence = _col(state=ABSENT, columns=(), column_ref="", evidence=None,
                    evidence_label="").evidence_sentence
    assert "cán bộ" in sentence.lower()


def test_assigned_state_is_the_default_so_the_sentence_path_is_the_common_one():
    assert _col().state == ASSIGNED


# ─────────────────── thẻ "Căn cứ đọc file": xoá theo HÌNH DẠNG ───────────────────

def test_read_basis_no_longer_carries_the_summary_card_fields():
    """AC 2: khẳng định bằng trường dataclass, không bằng chuỗi HTML vắng mặt.

    Ba trường này chỉ tồn tại để đổ vào thẻ tổng hợp. Còn chúng trên `ReadBasis` thì thẻ
    dựng lại được bất cứ lúc nào, và `match_source_label` là trường ĐI STALE: nó mô tả cả
    file bằng tên một tầng, trong khi mỗi cột có căn cứ riêng.
    """
    names = {f.name for f in dataclasses.fields(ReadBasis)}

    assert "match_source_label" not in names
    assert "template_name" not in names
    assert "layout_label" not in names


def test_the_page_level_restatement_constant_is_gone():
    """AC 3: `MATCH_SOURCE_LABEL_VI` nói lại cùng năm nguồn ở mức trang."""
    import app.pipeline.file_page as fp

    assert not hasattr(fp, "MATCH_SOURCE_LABEL_VI")
    assert "MATCH_SOURCE_LABEL_VI" not in fp.__all__


def test_read_basis_still_carries_what_the_sheet_form_needs():
    """Xoá theo thẻ, không xoá theo tên. `sheet`/`sheet_pinned` còn dùng ở biểu mẫu chọn trang."""
    names = {f.name for f in dataclasses.fields(ReadBasis)}

    assert {"sheet", "sheet_pinned", "columns", "needs_confirmation"} <= names


# ─────────────────── dòng trạng thái dưới lưới + liên kết cẩm nang ───────────────────

def test_the_file_page_drops_the_summary_card_heading(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_DETAIL)

    page = client.get(file_page_url("DN_EP", fid))

    assert page.status_code == 200
    assert "Căn cứ đọc file" not in page.text


def test_the_status_line_carries_the_sheet_and_the_row_count(env):
    """AC 4: thứ KHÔNG thuộc về từng trường khai gộp về một dòng dưới lưới."""
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_DETAIL, row_count=42)

    text = client.get(file_page_url("DN_EP", fid)).text

    assert "fp-status" in text
    assert "BCQT_NVL" in text
    assert "42" in text


def test_a_file_never_read_still_explains_itself_on_the_status_line(env):
    """Nhánh `else` của thẻ cũ là chỗ DUY NHẤT ca này tự nói ra.

    Bảng gán cột chỉ render trong `{% if basis.columns %}`, nên xoá thẻ mà không chuyển
    câu này đi thì file chưa đọc được ra một trang chỉ có lưới, không một chữ giải thích.
    """
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=None, row_count=None)

    text = client.get(file_page_url("DN_EP", fid)).text

    assert "fp-status" in text
    assert "chưa đọc file này lần nào" in text.lower()


def test_the_screen_links_to_the_manual_section_that_defines_the_terms(env):
    """AC 5: mục B7 của cẩm nang có sẵn bảng định nghĩa đúng bốn thuật ngữ."""
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_DETAIL)

    text = client.get(file_page_url("DN_EP", fid)).text

    assert "/static/docs/huong-dan/index.html#b7" in text


def test_the_sentence_reaches_the_rendered_page(env):
    """Câu phải đi tới màn hình, không dừng ở tầng dữ liệu."""
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_DETAIL)

    text = client.get(file_page_url("DN_EP", fid)).text

    assert "cùng dấu" in text


def test_the_data_screen_tooltip_explains_the_term_instead_of_repeating_it(env):
    """Tooltip cũ đọc ra "…: nguồn Khớp tiêu đề" — đúng bằng chữ đã hiện trên chip (#120).

    Chip giữ chữ ngắn vì câu không nhét vừa chip, nên nghĩa đi vào `title`. Câu tra theo mã
    nguồn THÔ lúc render: `parse_detail` của file nạp trước #120 chỉ lưu nhãn ngắn, không
    lưu câu nào, nên tra lúc render là đường duy nhất để file cũ cũng đọc được nghĩa.

    Tooltip hover CHƯA đạt "nghĩa cạnh nó" của AC 6 — đưa câu thành chữ hiện được ở màn
    này là đổi bố cục, tách vé riêng. Test này chốt mức vé #120 nhận, không hơn.
    """
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    _register_for_data_screen()

    text = client.get("/companies/DN_EP/data?year=2025&table=m15").text

    assert "nguồn Khớp tiêu đề" not in text      # không lặp lại chính thuật ngữ
    assert "khớp nhãn mong đợi của trường" in text
    assert "Khớp tiêu đề" in text                # chip vẫn giữ chữ ngắn


def test_the_status_line_adds_no_badge_and_no_axis(env):
    """#119 đếm nhãn trên TOÀN trang. Dòng trạng thái là câu, không phải nhãn thứ tư."""
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_DETAIL)

    text = client.get(file_page_url("DN_EP", fid)).text
    start = text.index("fp-status")

    assert "badge" not in text[start:start + 600]
    assert "data-axis" not in text[start:start + 600]
