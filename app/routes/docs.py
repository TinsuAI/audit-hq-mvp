"""Routes thư viện tài liệu.

Văn bản pháp lý + phương pháp luận: file .md trong `docs/`, render bằng
`python-markdown`. Cẩm nang hướng dẫn sử dụng là NGOẠI LỆ — trang HTML tự chứa dưới
`/static` (xem GUIDE_URL), slug cũ trả redirect để link đã phát ra ngoài vẫn chạy.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import SessionUser, require_user
from app.version import VERSION, version_string

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR.parent / "docs"

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()

# Cẩm nang hướng dẫn KHÔNG phải file .md: là trang HTML tự chứa (mục lục bên trái,
# ô tìm kiếm, ảnh chụp có khung đỏ + số thứ tự khớp từng bước) ở
# `app/static/docs/huong-dan/`. Thư mục đó copy sang host tĩnh khác chạy được nguyên vẹn.
GUIDE_SLUG = "huong-dan-su-dung"
GUIDE_URL = "/static/docs/huong-dan/index.html"

# Mỗi entry: slug → (file, title, description, category).
# category: "guide" (hướng dẫn) | "methodology" (phương pháp luận) | "legal" (văn bản pháp lý).
# Whitelist — chỉ slug ở đây mới được render. Thêm tài liệu mới: thêm 1 entry.
PUBLIC_DOCS: dict[str, tuple[str, str, str, str]] = {
    GUIDE_SLUG: (
        "",  # trang HTML riêng, không render markdown
        "Cẩm nang sử dụng Audit-HQ",
        "Hướng dẫn từng bước cho cán bộ và quản trị viên, mỗi thao tác kèm ảnh chụp "
        "có đánh số đúng chỗ cần bấm: đăng nhập, nạp dữ liệu, chạy kiểm tra, đọc điểm "
        "và phát hiện, xử lý truy nguồn, xuất kiến nghị.",
        "guide",
    ),
    "scoring-methodology": (
        "scoring-methodology.md",
        "Phương pháp tính điểm rủi ro",
        "Cách Audit-HQ tính điểm 0-1000 cho mỗi (DN, năm), giải thích "
        "công thức rate-based và 5 hạng cảnh báo.",
        "methodology",
    ),
    "tt-38-2015-tt-btc": (
        "tt-38-2015-tt-btc.md",
        "TT 38/2015/TT-BTC — Thủ tục hải quan, kiểm tra giám sát",
        "Khung pháp lý xương sống. Định nghĩa BCQT, Mẫu 15/15a/16, "
        "mã loại hình tờ khai (E11-E62, A42, B13) và phương trình cân đối kho.",
        "legal",
    ),
    "tt-39-2018-tt-btc": (
        "tt-39-2018-tt-btc.md",
        "TT 39/2018/TT-BTC — Sửa đổi TT 38/2015",
        "Sửa đổi quan trọng: bãi bỏ thông báo định mức trước, yêu cầu số liệu "
        "BCQT khớp chứng từ kế toán, lưu giữ chứng từ 5 năm.",
        "legal",
    ),
    "tt-81-2019-tt-btc": (
        "tt-81-2019-tt-btc.md",
        "TT 81/2019/TT-BTC — Quản lý rủi ro nghiệp vụ hải quan",
        "Quy định 5 Mức tuân thủ pháp luật + 9 Hạng rủi ro của TCHQ. "
        "Tham chiếu khi giải thích chỉ số rủi ro của Audit-HQ.",
        "legal",
    ),
}

CATEGORY_LABEL: dict[str, str] = {
    "guide": "Hướng dẫn sử dụng",
    "methodology": "Phương pháp luận",
    "legal": "Văn bản pháp lý",
}
CATEGORY_ORDER = ["guide", "methodology", "legal"]


@lru_cache(maxsize=8)
def _render_doc(filename: str) -> str:
    """Đọc .md từ disk + render sang HTML. Cache vì file ít thay đổi.

    Cache invalidate khi process restart — đủ cho deploy cycle.
    """
    md_path = DOCS_DIR / filename
    if not md_path.exists():
        raise FileNotFoundError(str(md_path))
    text = md_path.read_text(encoding="utf-8")
    return markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        output_format="html5",
    )


@router.get("/tai-lieu", response_class=HTMLResponse)
def docs_index(
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    """Index trang liệt kê toàn bộ tài liệu công khai, nhóm theo category."""
    by_category: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_ORDER}
    for slug, (_filename, title, description, category) in PUBLIC_DOCS.items():
        by_category.setdefault(category, []).append(
            {
                "slug": slug,
                "title": title,
                "description": description,
                "href": GUIDE_URL if slug == GUIDE_SLUG else f"/tai-lieu/{slug}",
            }
        )
    sections = [
        {"key": cat, "label": CATEGORY_LABEL.get(cat, cat), "entries": entries}
        for cat in CATEGORY_ORDER if (entries := by_category.get(cat, []))
    ]
    return templates.TemplateResponse(
        request,
        "docs_index.html",
        {"user": user, "sections": sections},
    )


@router.get("/tai-lieu/{slug}", response_class=HTMLResponse, response_model=None)
def render_doc(
    slug: str,
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse | RedirectResponse:
    entry = PUBLIC_DOCS.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Không có tài liệu '{slug}'")
    if slug == GUIDE_SLUG:
        # Cẩm nang là trang HTML riêng — giữ URL cũ chạy được cho link đã phát ra ngoài.
        return RedirectResponse(url=GUIDE_URL, status_code=307)
    filename, title, _description, _category = entry
    try:
        html_body = _render_doc(filename)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail=f"File tài liệu không tồn tại: {filename}",
        ) from None
    return templates.TemplateResponse(
        request,
        "docs_page.html",
        {"user": user, "title": title, "html_body": html_body, "slug": slug},
    )
