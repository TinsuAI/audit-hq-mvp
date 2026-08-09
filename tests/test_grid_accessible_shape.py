"""Lưới xem trước KHAI RA ĐƯỢC: vai, tên, số dòng, số cột — và nhãn cột thành CHỮ (#123).

Trước vé này vùng chứa lưới, ô góc, vùng số dòng và toàn bộ ô là `<div>` trần: không vai,
không tên, không số dòng/số cột. Công cụ hỗ trợ đọc ra một khối rỗng, còn nghĩa "hệ thống
đọc cột này thành trường gì, cột còn chờ xác nhận không" thì nằm trong `title` — chỉ chuột
mới lấy được.

Khẳng định ở BA đầu, vì không đầu nào một mình đủ:

* **template** — điểm neo `#cell-grid` khai `role`, tên, `aria-rowcount`, `aria-colcount`;
  đây là phần khẳng định được mà không cần trình duyệt (AC 1);
* **payload** — chú giải cột và hai số tổng đi ra từ máy chủ, đọc thẳng từ route (AC 3, AC 4);
* **mã nguồn lưới** — `cell-grid.js` đóng đúng hai số đó vào đúng hai thuộc tính template đã
  khai, và đặt vai cho từng phần nó dựng ra.

**KHÔNG phủ được ở đây** — tồn dư đã biết, RỘNG HƠN câu chữ của AC 5 ("số do JS đóng vào lúc
chạy thật"): mọi thứ chỉ có lúc chạy đều nằm ngoài, gồm hai số thật, các vai lưới đặt cho phần
nó dựng, phép gắn nhãn vào tiêu đề, và chiều cao tiêu đề nới ra cho dòng nhãn. `TestClient`
không chạy JavaScript và bộ test không có trình duyệt, nên đầu thứ ba ghim CƠ CHẾ ở mức mã
nguồn: mỗi khẳng định bám vào một mắt CÓ THẬT của chuỗi — dựng phần tử, GẮN nó vào cây, và
GỌI hàm — vì #122 đã cho thấy chuỗi chết ở mắt nào cũng im lặng. Tên thuộc tính và tên khoá
payload đối chiếu giữa các đầu chứ không ghim thành hằng riêng trong test.

Nhãn cột chỉ hiện khi công tắc "Hiện cột hệ thống đang đọc" bật — đó là thiết kế từ #92, và
AC 2 đạt vì nghĩa THÔI sống riêng trong `title`, không phải vì nhãn hiện sẵn.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company
from app.pipeline.file_page import AXES, file_page_url, file_read_basis
from app.settings import settings
from tests.excel_fixtures import write_xlsx
from tests.helpers import grid_body, grid_source
from tests.test_file_page import _M15_DETAIL, REL_DIR, _register, _row

# Câu chỉ sống trong `title` của tiêu đề cột trước vé này — nghĩa "cột còn chờ xác nhận"
# nay là nhãn trục *việc còn lại*, dựng ở máy chủ như mọi nhãn khác.
TOOLTIP_ONLY_SENTENCE = "còn chờ cán bộ xác nhận"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    from app.adapters import cell_window

    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    cell_window.reset_build_locks()
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_FP", name="Trang file", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _seed(root: Path, rows: list[list] | None = None) -> int:
    """File Mẫu 15 có ĐÚNG một cột còn chờ xác nhận và một cột không còn việc gì."""
    write_xlsx(root / REL_DIR / "m15.xlsx", rows or [["Mã", 1]], sheet_name="BCQT_NVL")
    return _register(parse_detail=_M15_DETAIL)


def _page(client, fid: int) -> str:
    r = client.get(file_page_url("DN_FP", fid))
    assert r.status_code == 200
    return r.text


def _mount_tag(text: str) -> str:
    tag = re.search(r"<div[^>]*id=\"cell-grid\"[^>]*>", text)
    assert tag, "trang không có điểm neo lưới"
    return tag.group(0)


def _attrs(tag: str) -> dict[str, str]:
    return {
        m.group(1): html.unescape(m.group(3))
        for m in re.finditer(r"([a-z-]+)=([\"'])(.*?)\2", tag, re.S)
    }


def _marks(text: str) -> dict[str, dict]:
    return json.loads(_attrs(_mount_tag(text))["data-mapped-columns"])


# ───────────────────── điểm neo tự khai mình (AC 1) ─────────────────────

def test_the_grid_mount_declares_a_role_a_name_and_both_counts(env):
    """AC 1. Bốn thứ, khai ở template nên khẳng định được mà không cần trình duyệt."""
    client, root = env
    fid = _seed(root)

    attrs = _attrs(_mount_tag(_page(client, fid)))

    assert attrs["role"]
    assert attrs["aria-label"]
    assert "aria-rowcount" in attrs
    assert "aria-colcount" in attrs


def test_the_name_says_which_file_the_grid_is_showing(env):
    """Một cái tên chung ("lưới") không phân biệt được gì — trang nào cũng có đúng một lưới,
    nhưng cái tên là thứ đọc lên khi con trỏ đi vào vùng, và file là thứ đang xem."""
    client, root = env
    fid = _seed(root)

    assert "m15.xlsx" in _attrs(_mount_tag(_page(client, fid)))["aria-label"]


def test_the_grid_does_not_claim_a_role_it_cannot_keep(env):
    """`role="grid"` hứa điều hướng bàn phím ở cấp ô. ADR #29 đã loại roving tabindex trên
    lưới ảo hoá khỏi phạm vi, nên khai `grid` là khai một khả năng không có."""
    client, root = env
    fid = _seed(root)

    assert _attrs(_mount_tag(_page(client, fid)))["role"] == "table"


def test_the_counts_start_at_unknown_because_the_page_never_opens_the_file(env):
    """Máy chủ dựng trang mà KHÔNG mở file (#91): ô đi qua điểm cuối cửa sổ, và lượt trích
    xuất đầu trả 202 rồi poll. `-1` là "chưa biết" theo ARIA — khai `0` là nói file rỗng."""
    client, root = env
    fid = _seed(root)

    attrs = _attrs(_mount_tag(_page(client, fid)))

    assert attrs["aria-rowcount"] == "-1"
    assert attrs["aria-colcount"] == "-1"


def test_the_wait_card_is_not_a_child_of_the_table(env):
    """Con của `role="table"` phải là dòng hoặc nhóm dòng. Màn chờ trích xuất không phải
    dòng nào, nên nó nằm NGOÀI điểm neo và chồng lên bằng `.cg-stack` — và lưới tra nó theo
    đúng cái `id` template phát ra."""
    client, root = env
    fid = _seed(root)

    text = _page(client, fid)
    tag = _mount_tag(text)
    overlay_id = re.search(r"getElementById\('(cg-[a-z]+)'\)", grid_body("build")).group(1)

    assert f'id="{overlay_id}"' in text
    assert text[text.index(tag) + len(tag):].lstrip().startswith("</div>"), (
        "điểm neo lưới phải rỗng ở phía máy chủ — mọi thứ trong nó là dòng lưới dựng ra"
    )


# ───────────────────── nhãn cột gập vào ba trục (AC 2, AC 3) ─────────────────────

def test_the_grid_reads_its_column_labels_from_the_field_row_property(env):
    """AC 3. Chú giải cột của lưới lấy từ CHÍNH `BasisColumn.labels` — cùng property dòng
    trường của bảng gán cột đọc. Dựng lại một bộ từ vựng riêng cho lưới thì hai chỗ nói về
    cùng một cột lệch nhau mà không chỗ nào bắt được."""
    client, root = env
    fid = _seed(root)

    marks = _marks(_page(client, fid))
    basis = {c.field: c for c in file_read_basis(_row(fid)).columns}

    for mark in marks.values():
        expected = [
            {"axis": lb.axis, "text": lb.text} for lb in basis[mark["field"]].labels
        ]
        assert mark["labels"] == expected


def test_the_grid_labels_stay_on_the_three_axes(env):
    """Không trục thứ tư. Cột còn chờ xác nhận nói ở trục *việc còn lại*; cột không còn việc
    gì không đeo nhãn nào — hiện theo ngoại lệ, đúng như dòng trường (#119)."""
    client, root = env
    fid = _seed(root)

    marks = _marks(_page(client, fid))

    assert marks["8"]["labels"] and marks["1"]["labels"] == []
    for mark in marks.values():
        for label in mark["labels"]:
            assert label["axis"] in AXES


def test_the_boolean_the_grid_used_to_invent_for_itself_is_gone(env):
    """Cờ `needs` là bộ từ vựng thứ tư: máy chủ gửi một boolean, JavaScript tự đặt câu chữ
    quanh nó, nên không phép so nào bắt được khi câu đó lệch với dòng trường."""
    client, root = env
    fid = _seed(root)

    for mark in _marks(_page(client, fid)).values():
        assert "needs" not in mark


def test_a_column_label_is_text_in_the_page_not_a_tooltip():
    """AC 2. Nhãn đi vào `textContent` kèm trục; `title` chỉ được lặp lại chữ đang hiện (tên
    trường bị bề ngang cột cắt), không được mang câu nào của riêng nó.

    Đặt chữ vào phần tử là CHƯA ĐỦ — dựng xong mà không gắn vào tiêu đề thì trang không có
    chữ nào, và đó là kiểu chết im lặng của #122. Nên khẳng định cả phép gắn."""
    body = grid_body("columnHeader")

    assert re.search(r"\.textContent\s*=\s*lb\.text", body)
    assert "'data-axis'" in body
    assert "th.appendChild(label)" in body, "nhãn dựng ra mà không gắn vào tiêu đề cột"
    assert "line.appendChild(tag)" in body, "tên trường dựng ra mà không gắn vào tiêu đề"
    assert not re.search(r"\.title\s*=\s*['\"]", body), (
        "một câu chỉ có trong tooltip là đúng lỗi vé này sinh ra để sửa"
    )


def test_the_second_line_of_the_header_is_opened_before_a_label_is_drawn():
    """Nhãn chiếm dòng thứ hai của tiêu đề, mà `.cg-col` cắt phần tràn: không nới chiều cao
    thì nhãn nằm trong DOM và không ai thấy — cùng một kết cục với việc không dựng nó.

    Hai chỗ phải nới: lúc cửa sổ đầu về (mới biết bản đồ cột nào nằm trong trang tính) và
    lúc cán bộ bật công tắc hiện cột đang đọc."""
    assert "applyHeadHeight()" in grid_body("onWindow")
    assert "applyHeadHeight()" in grid_body("wireControls")
    assert re.search(r"<\s*total", grid_body("anyColumnLabelled")), (
        "chỉ số cột phải SO với tổng số cột: nới tiêu đề theo một cột nằm ngoài trang "
        "tính là chừa một dòng trống cả lượt xem"
    )


def test_the_tooltip_only_sentence_is_gone_from_the_grid_script():
    assert TOOLTIP_ONLY_SENTENCE not in grid_source()


# ───────────────────── lưới đặt vai cho thứ nó dựng ra ─────────────────────

def test_every_layer_the_grid_builds_says_what_it_is():
    """Khung và lớp dịch chuyển là hình, không phải bảng: chúng nhường vai cho con. Ô góc và
    vùng số dòng lặp lại `aria-rowindex` bằng hình nên bị giấu, không đọc lên hai lần."""
    body = grid_body("build")

    assert body.count("'rowgroup'") == 2, "hàng tiêu đề cột và vùng ô là hai nhóm dòng"
    assert re.search(r"headInner\.setAttribute\('role', 'row'\)", body)
    assert body.count("'presentation'") == 2
    assert re.search(r"corner\.setAttribute\('aria-hidden', 'true'\)", body)
    assert re.search(r"side\.setAttribute\('aria-hidden', 'true'\)", body)


def test_a_cell_sits_inside_a_row_that_carries_the_sheet_row_number():
    """`role="row"` rỗng không đọc ra dòng nào, nên ô phải nằm TRONG dòng — trước vé này ô là
    một biển phẳng định vị tuyệt đối. Lưới chỉ giữ vài chục dòng trong DOM nên vị trí không
    suy ra được từ thứ tự phần tử: `aria-rowindex` / `aria-colindex` nói ra vị trí thật."""
    body = grid_body("render")

    assert re.search(r"tr\.setAttribute\('role', 'row'\)", body)
    assert re.search(r"tr\.setAttribute\('aria-rowindex', String\(r \+ 1\)\)", body)
    assert re.search(r"cell\.setAttribute\('role', 'cell'\)", body)
    assert re.search(r"cell\.setAttribute\('aria-colindex', String\(cc \+ 1\)\)", body)
    assert "tr.appendChild(cell)" in body


def test_a_column_header_is_a_column_header():
    """Tiêu đề cột là chỗ duy nhất lưới nói cột này đọc thành trường gì; đọc một ô mà không
    kèm tên cột thì con số trong ô không nói được nó là số của cái gì."""
    body = grid_body("columnHeader")

    assert re.search(r"setAttribute\('role', 'columnheader'\)", body)
    assert re.search(r"setAttribute\('aria-colindex', String\(colIndex \+ 1\)\)", body)


# ───────────────────── hai số thật đi từ payload vào thuộc tính (AC 4) ─────────────────────

def test_the_window_payload_carries_the_two_counts_the_grid_injects(env):
    """AC 4. Số dòng/số cột do JS đóng vào lấy từ ĐÂY, nên đây là chỗ ghim được chúng."""
    client, root = env
    fid = _seed(root, rows=[["Mã", "SL"], ["A", 1], ["B", 2]])

    body = client.get(f"/companies/DN_FP/documents/file/{fid}/cells?sheet=0").json()

    assert body["total_rows"] == 3
    assert body["total_cols"] == 2


def test_the_grid_injects_those_counts_into_the_attributes_the_template_declares(env):
    """Đầu kia của cùng mối nối: khoá của payload và tên thuộc tính của template đều đọc RA
    TỪ mã nguồn lưới rồi đem đối chiếu, nên đổi tên ở một bên mà quên bên kia là đỏ."""
    client, root = env
    fid = _seed(root)
    body = grid_body("setDimensions")

    payload = client.get(f"/companies/DN_FP/documents/file/{fid}/cells?sheet=0").json()
    attrs = _attrs(_mount_tag(_page(client, fid)))

    for key, attr in (("total_rows", "aria-rowcount"), ("total_cols", "aria-colcount")):
        assert re.search(rf"setAttribute\('{attr}', String\(data\.{key}\)\)", body)
        assert key in payload
        assert attr in attrs
    # Hàm còn đó mà không ai gọi thì hai số đứng nguyên ở `-1` suốt lượt xem — kiểu chết
    # im lặng thứ hai của #122, và chỉ khẳng định thân hàm thì không bắt được.
    assert "setDimensions(data)" in grid_body("onWindow")


def test_the_row_count_the_grid_speaks_is_the_one_the_status_line_writes():
    """Hàng chữ cái cột KHÔNG tính vào `aria-rowcount`: tính nó thì mọi `aria-rowindex` lệch
    1 so với số dòng đang hiện ở lề trái và so với dòng trạng thái ("12.345 dòng × 20 cột"),
    mà ở trang tính thì số dòng chính là danh tính của dòng."""
    injected = grid_body("setDimensions")
    written = grid_body("renderStatus")

    assert "+ 1" not in injected
    assert "total_rows" in injected and "total_rows" in written
    assert "total_cols" in injected and "total_cols" in written
