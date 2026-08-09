"""Đường đi của BÀN PHÍM qua trang (#126).

Ba khoản, cùng một triệu chứng: cán bộ dùng bàn phím phải đi qua thứ không phải việc của
họ trước khi tới việc của họ.

1. Không có liên kết nhảy tới nội dung → mỗi trang là bảy chặng tab qua menu.
2. Thanh trợ lý khai `aria-hidden="true"` (tức "không tồn tại") mà sáu điều khiển bên
   trong vẫn nhận được focus — hai câu ngược nhau, và focus rơi vào một thanh đang đóng.
3. Trang file tải cả thanh trợ lý dù trợ lý không đọc được file đang mở.

Khẳng định vào CẤU TRÚC (thuộc tính, đích liên kết, tệp được nạp), không vào câu chữ.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import file_page_url
from tests.conftest import AppDb
from tests.helpers import drain_jobs, m15_xlsx_bytes, upload_and_ingest

_CODE = "DN_KB"

#: Thẻ nhận focus mặc định. `<a>` chỉ nhận khi có `href`.
_FOCUSABLE = re.compile(
    r"<(button|select|textarea)\b[^>]*>|<a\b[^>]*\shref=[^>]*>|<input\b[^>]*>",
    re.I | re.S,
)


@pytest.fixture
def client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=_CODE, name="Bàn phím", tax_id="1"))
        db.commit()
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return c


def _file_id(app_db: AppDb, client: TestClient) -> int:
    upload_and_ingest(client, _CODE, "Mau15_NVL.xlsx", m15_xlsx_bytes())
    drain_jobs()
    with app_db.SessionLocal() as db:
        company = db.query(Company).filter_by(code=_CODE).one()
        return db.query(DataFile).filter_by(company_id=company.id).one().id


# ───────────────────────── skip-link ─────────────────────────

def test_skip_link_is_the_first_focusable_thing_and_points_at_the_main_region(
    client: TestClient,
):
    html = client.get("/companies").text

    first = _FOCUSABLE.search(html)
    assert first is not None
    assert 'class="skip-link"' in first.group(0), first.group(0)

    target = re.search(r'<a class="skip-link" href="#([^"]+)"', html)
    assert target is not None
    anchor = target.group(1)
    # Đích phải TỒN TẠI và phải nhận được focus — thiếu `tabindex` thì trình duyệt cuộn
    # tới nơi nhưng vòng tab vẫn ở đầu trang.
    main = re.search(r"<main\b[^>]*>", html)
    assert main is not None
    assert f'id="{anchor}"' in main.group(0), main.group(0)
    assert 'tabindex="-1"' in main.group(0), main.group(0)


def test_the_skip_link_is_reachable_by_focus_not_hidden_outright() -> None:
    """`display: none` / `visibility: hidden` là rời khỏi chuỗi tab, tức không bao giờ
    hiện ra được. Nó phải chỉ dời khỏi khung nhìn."""
    from tests.test_static_assets import _declaration, _rule_body

    body = _rule_body(".skip-link")
    assert _declaration(body, "display") != "none"
    assert _declaration(body, "visibility") != "hidden"
    assert _declaration(body, "position") == "absolute"
    assert _rule_body(".skip-link:focus"), ".skip-link:focus không có rule nào"


# ───────────────────────── thanh trợ lý ─────────────────────────

def _panel(html: str) -> str:
    return html.split('<aside id="ai-panel"', 1)[1].split("</aside>", 1)[0]


def _focusable_count(fragment: str) -> int:
    """Số điều khiển NHẬN ĐƯỢC focus, bỏ qua cả cây con nằm dưới một phần tử `hidden`.

    Đếm bằng cách duyệt cây, không bằng biểu thức chính quy: `#ai-history-panel` có div
    lồng nhau, và một mẫu "tới `</div>` gần nhất" cắt nhầm ngay ở div con đầu tiên.
    """
    from html.parser import HTMLParser

    class Counter(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.depth = 0
            self.hidden_at: int | None = None
            self.count = 0

        def handle_starttag(self, tag: str, attrs) -> None:
            attributes = dict(attrs)
            if tag not in {"input", "img", "br", "hr", "meta", "link"}:
                self.depth += 1
            if "hidden" in attributes and self.hidden_at is None:
                self.hidden_at = self.depth
                return
            if self.hidden_at is not None:
                return
            if tag in {"button", "select", "textarea", "input"}:
                self.count += 1
            elif tag == "a" and attributes.get("href") is not None:
                self.count += 1

        def handle_endtag(self, tag: str) -> None:
            if self.hidden_at is not None and self.depth == self.hidden_at:
                self.hidden_at = None
            self.depth -= 1

    counter = Counter()
    counter.feed(f"<div>{fragment}</div>")
    return counter.count


def test_the_hidden_assistant_panel_is_out_of_the_tab_order(client: TestClient):
    html = client.get("/companies").text

    opening = html.split('<aside id="ai-panel"', 1)[1].split(">", 1)[0]
    assert 'aria-hidden="true"' in opening
    assert re.search(r"\binert\b", opening), opening

    # Các điều khiển đó vẫn còn trong HTML — `inert` là thứ đưa chúng khỏi chuỗi tab.
    # Đếm để phép đo nói được là nó che đúng số điều khiển vé nêu, không phải 0.
    #
    # SÁU là số ở HTML máy chủ dựng. Lúc chạy có thể là bảy: `renderScopeBar` bỏ `hidden`
    # khỏi `#ai-scope-bar` ngay ở `init()`, không đợi thanh mở. Con số không phải điều
    # kiện của bản vá — `inert` che CẢ CÂY CON nên nó không phụ thuộc số điều khiển đang
    # hiện; đây chỉ là phép đo đối chiếu với con số vé nêu.
    assert _focusable_count(_panel(html)) == 6


def test_opening_and_closing_the_panel_move_inert_with_aria_hidden() -> None:
    """Hai thuộc tính phải đổi ở CÙNG một chỗ; tách ra là chúng đi lệch nhau."""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "sidebar.js"
    ).read_text(encoding="utf-8")

    def body_of(name: str) -> str:
        start = source.index(f"function {name}(")
        depth, out = 0, []
        for ch in source[start:]:
            out.append(ch)
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
        return "".join(out)

    opened = body_of("openPanel")
    assert "aria-hidden', 'false'" in opened
    assert "removeAttribute('inert')" in opened

    closed = body_of("closePanel")
    assert "aria-hidden', 'true'" in closed
    assert "setAttribute('inert'" in closed
    # Trả focus TRƯỚC khi khai `inert`: focus đang nằm trong thanh, mà `inert` làm cả cây
    # con hết nhận focus, nên trình duyệt đẩy focus về `<body>` và vòng tab quay lại đầu
    # trang. Thứ tự là phần khẳng định, không chỉ sự có mặt.
    assert closed.index("focus()") < closed.index("setAttribute('inert'")


# ───────────────────────── trang file không tải thanh trợ lý ─────────────────────────

def test_the_file_page_does_not_ship_the_assistant(app_db: AppDb, client: TestClient):
    fid = _file_id(app_db, client)

    file_page = client.get(file_page_url(_CODE, fid)).text
    other_page = client.get(f"/companies/{_CODE}/documents").text

    assert 'id="ai-panel"' not in file_page
    for asset in ("/static/sidebar.js", "/static/chat-core.js", "/static/sidebar.css"):
        assert asset not in file_page, asset
        assert asset in other_page, f"{asset} phải còn ở các màn khác"


def test_the_unread_jobs_poll_is_untouched(client: TestClient):
    """Poll `/jobs/unread.json` mỗi 10 giây GIỮ NGUYÊN — ngoài phạm vi vé, cố ý."""
    html = client.get("/companies").text

    assert "/jobs/unread.json" in html
    assert "setInterval(update, 10000)" in html
