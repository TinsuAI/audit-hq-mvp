"""Cài đặt đọc file: một bộ chọn trang tính, ghim là hành động riêng (#124).

Trước vé này MỘT màn có HAI bộ chọn cùng liệt kê tên trang tính với hai hậu quả khác
nhau: hàng nút trên lưới đổi khung nhìn, `<select name="sheet">` ở thẻ phía dưới ghim
trang cho lượt nạp sau. Không chỗ nào trên màn nói ra sự khác nhau đó.

Gộp thành MỘT quan hệ: bộ chọn trên lưới đổi thứ ĐANG XEM (địa chỉ mang `?sheet=`),
còn ghim là một nút riêng trỏ vào trang đang xem, đi đường riêng
(`POST …/file/{id}/sheet`).

Ba nhóm khẳng định ở đây:

* `ReadSettings` — câu chữ và phép quyết định "đã đặt đúng chưa" ở mức dữ liệu, khẳng
  định được mà không phải dựng trang;
* trang đã dựng — một bộ chọn, vùng cài đặt thu/mở đúng trạng thái, bốn quy tắc về sổ
  quyết toán nói ở đúng trạng thái áp dụng, không chuỗi nào quá 200 ký tự;
* mối nối JS ↔ HTML — lấy lớp và id TỪ `cell-grid.js` rồi đối chiếu với trang, để đứt
  bên nào cũng đỏ (bài học #122/#123: mã chỉ chạy ở trình duyệt chết im lặng).

KHÔNG khẳng định được ở đây: bấm nút trên lưới có thật sự đổi khung nhìn mà không tải
lại trang hay không. `TestClient` không chạy JS — đó là tồn dư đã biết của vé, đo bằng
trình duyệt.
"""

from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import ReadSettings, file_page_url
from app.settings import settings
from tests.excel_fixtures import write_xlsx

GRID_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "cell-grid.js"

REL_DIR = "DN_RS/2025/BCQT"

_M15_DETAIL = {
    "sheet": "BCQT_NVL",
    "form_signature": "sig-m15",
    "column_map": {"material_code": 0, "production_out_qty": 1},
    "columns": [
        {"field": "material_code", "label": "Mã NVL",
         "evidence": "header-matched", "review": "verified"},
        {"field": "production_out_qty", "label": "Xuất SX",
         "evidence": "header-matched", "review": "verified"},
    ],
    "column_choices": [{"index": i, "header": f"cot{i}"} for i in range(4)],
}


def _settings(**kw) -> ReadSettings:
    base = dict(
        sheet="BCQT_NVL", sheet_pinned=False,
        sheet_names=("Phụ lục", "BCQT_NVL"), viewed="BCQT_NVL",
        book_shown=False, book=None, period_books=(), book_blocked=False,
    )
    return ReadSettings(**(base | kw))


# ─────────────────────── mức dữ liệu ───────────────────────

def test_a_sheet_and_a_book_that_are_both_set_collapse_the_region():
    """AC 3. Trang tính đã có, sổ không phải việc của file này → thu còn một dòng."""
    assert _settings().settled is True


def test_no_sheet_at_all_keeps_the_region_open():
    assert _settings(sheet=None, viewed="Phụ lục").settled is False


def test_a_pinned_sheet_that_left_the_file_keeps_the_region_open():
    """Ghim một trang rồi file được thay bằng bản không còn trang đó: lượt nạp sau
    không đọc được gì, và đó là trạng thái *đang sai* chứ không phải *chưa đặt*."""
    s = _settings(sheet="Cũ", sheet_pinned=True, viewed="Phụ lục")

    assert s.sheet_missing is True
    assert s.settled is False


def test_a_settlement_file_with_no_book_while_ingest_refuses_keeps_it_open():
    """AC 3. "Đang sai" của sổ = đúng điều kiện cổng nạp từ chối vì CHÍNH file này."""
    assert _settings(book_shown=True, book=None, book_blocked=True).settled is False
    assert _settings(book_shown=True, book="EPE", book_blocked=False).settled is True
    # Không phải file quyết toán → không có ô sổ để đặt, không giữ vùng mở.
    assert _settings(book_shown=False, book_blocked=True).settled is True


def test_the_summary_names_the_sheet_and_the_book():
    s = _settings(sheet_pinned=True, book_shown=True, book="EPE")

    assert "BCQT_NVL" in s.summary
    assert "ghim" in s.summary
    assert "EPE" in s.summary


def test_the_summary_says_one_book_when_blank_is_the_right_answer():
    assert "một sổ" in _settings(book_shown=True).summary.lower()
    assert "Chưa gán sổ" in _settings(book_shown=True, book_blocked=True).summary


def test_pinning_the_sheet_already_pinned_is_not_offered():
    """Ghim lại đúng trang đang ghim không đổi gì — nút đó phải câm."""
    assert _settings(sheet_pinned=True, viewed="BCQT_NVL").can_pin is False
    assert _settings(sheet_pinned=True, viewed="Phụ lục").can_pin is True
    # Chưa ghim thì ghim trang đang xem LUÔN có nghĩa, kể cả khi máy đang tự đọc nó.
    assert _settings(viewed="BCQT_NVL").can_pin is True
    assert _settings(viewed="").can_pin is False


def test_the_viewed_line_stays_quiet_when_it_would_repeat_the_read_line():
    assert _settings(viewed="BCQT_NVL").viewed_line == ""
    assert "Phụ lục" in _settings(viewed="Phụ lục").viewed_line


# ─────────────────────── trang đã dựng ───────────────────────

@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_RS", name="Cài đặt đọc", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _register(
    root: Path, *, detail: dict | None = None, sheet_override: str | None = None,
    book: str | None = None, slot: str = "m15", name: str = "m15.xlsx",
    status: str = "parsed",
) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    write_xlsx(
        root / rel, [["Mã", 1]], sheet_name="BCQT_NVL",
        extra_sheets={"Phụ lục": [["x"]]},
    )
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_RS").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot=slot,
            original_filename=name, stored_path=rel,
            size_bytes=(root / rel).stat().st_size,
            parse_status=status, row_count=1, book=book,
            sheet_override=sheet_override,
            parse_detail=json.dumps(detail or {}, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return row.id


def _page(client, fid: int, query: str = "") -> str:
    r = client.get(file_page_url("DN_RS", fid) + query)
    assert r.status_code == 200
    return r.text


def _region(text: str) -> str:
    """Vùng cài đặt đọc file, cắt từ trang đã dựng."""
    start = text.index('id="read-settings"')
    start = text.rindex("<details", 0, start)
    return text[start : text.index("</details>", start)]


def _blocks(region: str) -> list[str]:
    """Chữ của từng khối văn bản trong vùng — đơn vị mà cán bộ đọc thành một câu."""
    out = []
    for m in re.finditer(r"<(p|li|summary|label|h2)\b[^>]*>(.*?)</\1>", region, re.S):
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def test_the_page_has_exactly_one_sheet_picker(env):
    """AC 1 + AC 2. Bộ chọn trùng ở thẻ phía dưới đã xoá."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    text = _page(client, fid)

    assert "<select" not in text or 'name="sheet"' not in _selects(text)
    assert "Trang tính (sheet) được đọc" not in text     # nhãn của thẻ đã xoá
    # Mỗi trang tính xuất hiện ĐÚNG một lần như một thứ bấm được để đổi khung nhìn.
    picks = re.findall(r'data-sheet-name="([^"]*)"', text)
    assert picks == ["BCQT_NVL", "Phụ lục"]


def _selects(text: str) -> str:
    return " ".join(re.findall(r"<select\b[^>]*>", text))


def test_the_picker_marks_the_sheet_being_viewed(env):
    """Địa chỉ mang `?sheet=` là thứ nói trang nào đang xem — bộ chọn theo nó."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    tags = re.findall(r"<a\b[^>]*js-sheet-pick[^>]*>", _page(client, fid, "?sheet=0"))

    assert len(tags) == 2
    assert 'aria-current="true"' in tags[0] and 'data-sheet-index="0"' in tags[0]
    assert "aria-current" not in tags[1]


def test_pinning_targets_the_sheet_being_viewed(env):
    """AC 1. Ghim là hành động rõ ràng TRÊN TRANG ĐANG XEM, không phải một ô chọn khác."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    pin = re.search(r'<button\b[^>]*id="sheet-pin"[^>]*>', _page(client, fid, "?sheet=1"))

    assert pin, "không còn nút ghim trang"
    assert 'value="Phụ lục"' in pin.group(0)          # đúng trang đang xem
    assert 'form="fp-sheet-form"' in pin.group(0)     # đường riêng, không phải form gán cột


def test_the_region_collapses_when_the_sheet_and_the_book_are_right(env):
    """AC 3."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    region = _region(_page(client, fid))

    assert "<details" in region and " open" not in region.split(">", 1)[0]


def test_the_region_opens_when_no_sheet_was_identified(env):
    """AC 3. File chưa đọc ra trang nào → việc đầu tiên là chọn trang, nên mở sẵn."""
    client, root = env
    fid = _register(root, detail={}, status="error")

    region = _region(_page(client, fid))

    assert " open" in region.split(">", 1)[0]


def test_the_region_opens_when_this_file_is_the_one_missing_a_book(env):
    """AC 3 + AC 4. Cổng nạp dừng vì file này chưa có mã sổ → nói ngay, mở sẵn."""
    client, root = env
    tagged = _register(root, detail=_M15_DETAIL, slot="m16", name="m16.xlsx", book="EPE")
    fid = _register(root, detail=_M15_DETAIL)
    assert tagged != fid

    text = _page(client, fid)
    region = _region(text)

    assert " open" in region.split(">", 1)[0]
    assert "Cách sửa" in region


def test_the_four_book_rules_are_split_and_state_bound(env):
    """AC 4. Bốn quy tắc, mỗi cái nói ở trạng thái nó áp dụng — không phải một đoạn."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL, book="EPE")

    region = _region(_page(client, fid))

    assert "tất cả hoặc không" in region          # quy tắc 1 — luôn áp dụng ở ô sổ
    assert "một sổ, dùng chung" not in region     # quy tắc 2 — chỉ khi đang để trống
    assert "Cách sửa" not in region               # quy tắc 4 — chỉ khi đang sai


def test_the_blank_book_rule_speaks_where_blank_is_the_state(env):
    """AC 4, quy tắc 2."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    assert "một sổ, dùng chung" in _region(_page(client, fid))


def test_no_string_in_the_region_runs_past_two_hundred_characters(env):
    """AC 5. Đoạn dài nhất trước vé này là 559 ký tự, đọc ở mọi trạng thái."""
    client, root = env
    tagged = _register(root, detail=_M15_DETAIL, slot="m16", name="m16.xlsx", book="EPE")
    fid = _register(root, detail=_M15_DETAIL, sheet_override="BCQT_NVL")
    assert tagged != fid

    blocks = _blocks(_region(_page(client, fid)))

    assert blocks, "vùng cài đặt không có khối chữ nào — phép đo bên dưới vô nghĩa"
    too_long = [(len(b), b) for b in blocks if len(b) > 200]
    assert not too_long, too_long


# ─────────────────────── ghim đi đường riêng ───────────────────────

def test_pinning_a_sheet_writes_the_pin_and_queues_a_reingest(env):
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    r = client.post(
        f"{file_page_url('DN_RS', fid)}/sheet",
        data={"sheet": "Phụ lục"}, follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"].endswith("/documents#ky-2025")
    assert _stored(fid).sheet_override == "Phụ lục"
    assert _queued_ingests() == 1


def test_unpinning_hands_the_choice_back_to_the_system(env):
    client, root = env
    fid = _register(root, detail=_M15_DETAIL, sheet_override="Phụ lục")

    client.post(
        f"{file_page_url('DN_RS', fid)}/sheet", data={"sheet": ""},
        follow_redirects=False,
    )

    assert _stored(fid).sheet_override is None


def test_pinning_leaves_the_column_map_and_the_book_alone(env):
    """Đường riêng nên lượt ghim KHÔNG ghi đè ba thứ mà một biểu mẫu thiếu ô sẽ ghi đè."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL, book="EPE")

    client.post(
        f"{file_page_url('DN_RS', fid)}/sheet", data={"sheet": "Phụ lục"},
        follow_redirects=False,
    )

    row = _stored(fid)
    assert row.book == "EPE"
    assert row.parse_detail_obj["column_map"] == {"material_code": 0, "production_out_qty": 1}


def test_confirming_columns_does_not_drop_the_pinned_sheet(env):
    """Biểu mẫu gán cột không còn mang ô trang tính — vắng phải nghĩa là GIỮ NGUYÊN.

    Đây là lỗi mà việc xoá `<select name="sheet">` sinh ra nếu hợp đồng cũ giữ nguyên:
    ô vắng từng nghĩa là "bỏ ghim", nên mỗi lượt xác nhận cột sẽ lặng lẽ trả quyền chọn
    trang về cho máy.
    """
    client, root = env
    fid = _register(root, detail=_M15_DETAIL, sheet_override="Phụ lục")

    client.post(
        file_page_url("DN_RS", fid),
        data={"col_material_code": "0", "col_production_out_qty": "1"},
        follow_redirects=False,
    )

    assert _stored(fid).sheet_override == "Phụ lục"


def test_the_old_address_still_unpins_with_an_empty_sheet_field(env):
    """Địa chỉ cũ `/review` vẫn gửi ô trang tính, và ở đó "" vẫn nghĩa là bỏ ghim."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL, sheet_override="Phụ lục")

    client.post(
        f"{file_page_url('DN_RS', fid)}/review",
        data={"sheet": "", "col_material_code": "0", "col_production_out_qty": "1"},
        follow_redirects=False,
    )

    assert _stored(fid).sheet_override is None


def _stored(fid: int) -> DataFile:
    import app.database as dbmod

    with dbmod.SessionLocal() as db:
        row = db.get(DataFile, fid)
        db.expunge(row)
        return row


def _queued_ingests() -> int:
    import app.database as dbmod
    from app.models.job import Job, JobKind

    with dbmod.SessionLocal() as db:
        return db.query(Job).filter_by(kind=JobKind.INGEST).count()


# ─────────────────────── mối nối JS ↔ HTML ───────────────────────

@lru_cache(maxsize=1)
def _grid_source() -> str:
    return GRID_JS.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _functions() -> dict[str, str]:
    src = _grid_source()
    starts = [(m.group(1), m.start()) for m in re.finditer(r"^  function (\w+)\(", src, re.M)]
    return {
        name: src[pos : (starts[i + 1][1] if i + 1 < len(starts) else len(src))]
        for i, (name, pos) in enumerate(starts)
    }


def _body(name: str) -> str:
    fns = _functions()
    assert name in fns, f"`cell-grid.js` không còn hàm `{name}` — chuỗi bộ chọn đã đứt"
    return fns[name]


def test_the_class_the_grid_hooks_on_is_the_class_the_page_emits(env):
    """Lấy lớp TỪ JS rồi đối chiếu với trang: đứt bên nào cũng đỏ.

    Đổi lớp trong JS mà quên template, hoặc đổi trong template mà quên JS, thì
    `querySelectorAll` trả rỗng — không lỗi nào ném ra, bộ chọn chỉ thôi đổi tại chỗ.
    """
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    m = re.search(r"querySelectorAll\(\s*'\.([a-z0-9-]+)'", _body("wireSheetPicker"))
    assert m, "`wireSheetPicker` không truy phần tử nào nữa"
    hook = m.group(1)

    text = _page(client, fid)
    hooked = re.findall(rf'<a\b[^>]*class="[^"]*\b{re.escape(hook)}\b[^"]*"[^>]*>', text)

    # Mỗi trang tính đúng một liên kết, và mọi liên kết đều mang lớp nối.
    assert len(hooked) == len(re.findall(r'data-sheet-name="', text)) == 2


def test_the_picker_wiring_is_actually_called(env):
    """#123 chết vì thân hàm được ghim mà CHỖ GỌI thì không. Ghim cả chỗ gọi."""
    assert "wireSheetPicker()" in _body("wireControls") or "wireSheetPicker()" in _body("init")


def test_switching_sheets_retargets_the_pin_button(env):
    """Nút ghim luôn trỏ vào trang đang xem — nếu không, ghim một trang đang không xem."""
    client, root = env
    fid = _register(root, detail=_M15_DETAIL)

    assert "setPinTarget(" in _body("openSheet")
    m = re.search(r"getElementById\('([a-z-]+)'\)", _body("setPinTarget"))
    assert m, "`setPinTarget` không tìm nút nào"

    assert f'id="{m.group(1)}"' in _page(client, fid)


def test_the_grid_no_longer_builds_a_second_sheet_picker():
    """Bộ chọn dựng ở MÁY CHỦ. Hai chỗ dựng cùng một hàng nút là hai chỗ đi lệch nhau."""
    assert "renderSheets" not in _grid_source()
