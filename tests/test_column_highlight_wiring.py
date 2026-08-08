"""Chuỗi làm nổi cột: bộ chọn của một trường → cột đó sáng lên trong lưới cùng trang (#122).

Chuỗi `wireColumnInputs → setHighlight → showColumn` có sẵn trong `cell-grid.js` từ #92
nhưng CHẾT: nó truy `input.review-idx`, mà không template nào phát chuỗi đó kể từ khi màn
gán cột được dựng lại. `querySelectorAll` trả rỗng nên không có lỗi nào ném ra — cả chuỗi
cùng hai rule `.cg-col-hi` / `.cg-cell-hi` không đường nào tới.

Chết im lặng thì phải có test bắt được chính kiểu chết đó, nên ở đây khẳng định HAI ĐẦU
của mối nối và bắt chúng khớp nhau ở mức chuỗi:

* đầu JS — lớp mà `wireColumnInputs` truy, đọc thẳng từ `app/static/cell-grid.js`;
* đầu HTML — lớp mà biểu mẫu thật sự phát ra, đọc từ trang đã dựng.

Lấy lớp từ JS rồi đem đối chiếu với HTML (chứ không ghim một hằng trong test) làm mối nối
đứt ở bên nào cũng đỏ: đổi bộ chọn trong JS mà quên template, hoặc đổi class trong template
mà quên JS.

KHÔNG khẳng định được ở đây: cột có thật sự sáng lên và lưới có thật sự cuộn tới hay không.
`TestClient` không chạy JS, và bộ test không có trình duyệt. Test dưới ghim CƠ CHẾ ở mức
mã nguồn (`showColumn` chỉ động tới `scrollLeft`); việc nó hiện đúng trên màn hình thuộc vé
bằng chứng feature — đây là tồn dư đã biết của #122, không phải chỗ sót.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import file_page_url
from app.settings import settings
from tests.excel_fixtures import write_xlsx

GRID_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "cell-grid.js"

REL_DIR = "DN_HL/2025/BCQT"

# Bố cục Mẫu 16 có một trường đọc bằng TỔNG hai cột (ADR #25) — dòng duy nhất mà bộ chọn
# là ô nhập chỉ số chứ không phải `<select>`, nên cũng là dòng phải tự nói tiêu đề cột.
_DETAIL = {
    "sheet": "BCTT39",
    "form_signature": "sig-hl",
    "column_map": {
        "product_code": 1, "product_name": 2, "product_unit": 3, "material_code": 4,
        "material_name": 5, "material_unit": 6, "norm_qty": [7, 8],
    },
    "columns": [
        {"field": f, "evidence": "header-matched", "review": "verified"}
        for f in ("product_code", "product_name", "product_unit", "material_code",
                  "material_name", "material_unit", "norm_qty")
    ],
    "column_choices": [
        {"index": i, "header": f"cot{i}", "samples": ["x"]} for i in range(9)
    ],
}


# ─────────────────────── đọc mã nguồn lưới ───────────────────────

@lru_cache(maxsize=1)
def _grid_source() -> str:
    return GRID_JS.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _functions() -> dict[str, str]:
    """Thân từng hàm mức trên cùng của `cell-grid.js`, cắt theo cột thụt đầu dòng.

    Cắt thô có chủ ý: bộ test không nhúng trình phân tích JS, và một regex chặt hơn thì
    mọi lần sửa `cell-grid.js` sau này đỏ vì lý do không liên quan.
    """
    src = _grid_source()
    starts = [(m.group(1), m.start()) for m in re.finditer(r"^  function (\w+)\(", src, re.M)]
    return {
        name: src[pos : (starts[i + 1][1] if i + 1 < len(starts) else len(src))]
        for i, (name, pos) in enumerate(starts)
    }


def _body(name: str) -> str:
    fns = _functions()
    assert name in fns, f"`cell-grid.js` không còn hàm `{name}` — chuỗi làm nổi cột đã đứt"
    return fns[name]


def _picker_selector() -> str:
    """Bộ chọn mà `wireColumnInputs` dùng để tìm bộ chọn cột."""
    m = re.search(r"querySelectorAll\(\s*'([^']+)'", _body("wireColumnInputs"))
    assert m, "`wireColumnInputs` không truy phần tử nào nữa"
    return m.group(1)


def _hook_class() -> str:
    """Lớp nối chuỗi, lấy từ chính JS. Phải là MỘT lớp trần: `<select>` cũng là bộ chọn cột,
    nên bộ chọn có tiền tố thẻ (`input.x`, kiểu cũ) không bao giờ khớp một nửa số dòng."""
    sel = _picker_selector()
    assert re.fullmatch(r"\.[a-z0-9-]+", sel), (
        f"bộ chọn {sel!r} không phải một lớp trần — `<select>` sẽ không được nối"
    )
    return sel[1:]


# ─────────────────────── trang đã dựng ───────────────────────

@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_HL", name="Làm nổi cột", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _register(root: Path, detail: dict, *, name: str = "dm.xlsx") -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    write_xlsx(root / rel, [["Mã SP", "Mã NVL", "ĐM"], ["SP1", "MAT1", 1.5]])
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_HL").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="m16",
            original_filename=name, stored_path=rel,
            size_bytes=(root / rel).stat().st_size,
            parse_status="parsed", row_count=3, parse_layout="extended",
            parse_detail=json.dumps(detail, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return row.id


def _table(text: str) -> str:
    start = text.index('<table class="fieldmap-table"')
    return text[start : text.index("</table>", start)]


def _column_controls(text: str) -> list[str]:
    """Thẻ mở của mọi ô điều khiển mang vị trí cột mà cán bộ sửa được — bỏ ô ẩn."""
    tags = re.findall(r'<(?:input|select)\b[^>]*name="col_[a-z_]+"[^>]*>', text)
    return [t for t in tags if 'type="hidden"' not in t]


def _page(client, fid: int) -> str:
    r = client.get(file_page_url("DN_HL", fid))
    assert r.status_code == 200
    return r.text


# ─────────────────────── lớp nối chuỗi thật sự được phát ───────────────────────

def test_every_column_picker_carries_the_class_the_grid_hooks_on(env):
    """AC 3. Lớp lấy từ JS, đối chiếu với HTML — đứt bên nào cũng đỏ."""
    client, root = env
    fid = _register(root, _DETAIL)

    controls = _column_controls(_table(_page(client, fid)))
    hook = _hook_class()

    assert controls, "bảng gán cột không dựng ô điều khiển nào — phép so bên dưới vô nghĩa"
    for tag in controls:
        assert re.search(rf'class="[^"]*\b{re.escape(hook)}\b', tag), tag


def test_both_shapes_of_picker_are_hooked(env):
    """`<select>` (cột đơn) và ô nhập chỉ số (nhóm cột con) đều là bộ chọn cột."""
    client, root = env
    fid = _register(root, _DETAIL)

    table = _table(_page(client, fid))
    hook = _hook_class()
    hooked = [t for t in _column_controls(table)
              if re.search(rf'class="[^"]*\b{re.escape(hook)}\b', t)]

    assert any(t.startswith("<select") for t in hooked)
    assert any(t.startswith("<input") for t in hooked)


def test_nothing_outside_the_field_map_wears_the_hook(env):
    """Ô "Tới dòng", bộ chọn trang tính, ô mã sổ đều KHÔNG mang vị trí cột — nối chúng vào
    chuỗi là làm nổi một cột lấy từ số không liên quan."""
    client, root = env
    fid = _register(root, _DETAIL)

    text = _page(client, fid)
    hook = _hook_class()
    table = _table(text)

    assert text.count(hook) == table.count(hook)


# ─────────────────────── chuỗi trong lưới còn nối ───────────────────────

def test_the_picker_hook_reacts_to_both_typing_and_choosing():
    """AC 1. `<select>` phát `change`, ô nhập phát `input`; đưa focus vào là đủ để soi."""
    body = _body("wireColumnInputs")

    for event in ("input", "change", "focus"):
        assert re.search(rf"addEventListener\(\s*'{event}'", body), event
        assert "setHighlight" in body
    assert re.search(r"addEventListener\(\s*'blur'[^}]*setHighlight\(\s*''\s*\)", body), (
        "rời ô mà không tắt làm nổi thì cột sáng dính lại sau khi cán bộ đi chỗ khác"
    )


def test_the_hook_is_wired_during_grid_start_up():
    """Chuỗi chết kiểu thứ hai: lớp còn phát, hàm còn đó, nhưng không ai gọi nó."""
    assert "wireColumnInputs()" in _body("wireControls")
    assert "wireControls()" in _body("init")


def test_choosing_a_column_repaints_the_grid_and_brings_the_column_into_view():
    assert "showColumn" in _body("setHighlight")
    assert "render(" in _body("setHighlight")


def test_bringing_a_column_into_view_never_moves_the_row_position():
    """AC 2. Cán bộ đang đối chiếu một vùng dòng cụ thể — kéo họ về dòng 1 là bắt tìm lại."""
    body = _body("showColumn")

    assert "scrollLeft" in body
    assert "scrollTop" not in body


def test_a_column_is_only_brought_into_view_where_it_can_be_marked():
    """Chỉ số cột chỉ có nghĩa trên trang tính parser đọc — `isHighlighted` đã gác điều đó,
    và cú cuộn phải gác cùng điều kiện. Không thì lưới dời ngang mà không đánh dấu gì."""
    assert "onParsedSheet" in _body("showColumn")


# ─────────────────────── dòng trường đứng được một mình ───────────────────────

def test_a_group_row_names_every_column_it_sums_with_that_columns_header(env):
    """AC 5. Lưới là phần TĂNG THÊM: đường lạnh trả 202 rồi poll, nên trong lúc chờ trích
    xuất dòng trường vẫn phải tự nói nó đang đọc cột nào. `<select>` nói sẵn trong nhãn
    lựa chọn đang chọn; ô nhập chỉ số chỉ có `7,8` nên phải nói thêm."""
    client, root = env
    fid = _register(root, _DETAIL)

    table = _table(_page(client, fid))
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="col_norm_qty"' in r)

    assert "cột 7 «cot7»" in row
    assert "cột 8 «cot8»" in row


def test_a_column_outside_the_snapshot_is_named_without_a_header(env):
    """Vị trí đã lưu có thể trỏ ra ngoài ảnh chụp cột (lượt nạp sau đọc trang tính hẹp hơn).
    Không có tiêu đề để nói thì nói mỗi chỉ số, không bịa dấu «»."""
    client, root = env
    detail = dict(_DETAIL, column_map=dict(_DETAIL["column_map"], norm_qty=[7, 40]))
    fid = _register(root, detail)

    table = _table(_page(client, fid))
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="col_norm_qty"' in r)

    assert "cột 40" in row
    assert "cột 40 «" not in row


def test_the_dead_selector_is_gone_from_the_repo():
    """`input.review-idx` là chính chuỗi đã chết — còn sót một bản là còn một đường không tới."""
    assert "review-idx" not in _grid_source()
