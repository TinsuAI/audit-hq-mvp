"""Routes hiển thị tài liệu .md từ thư mục docs/.

Single source of truth: file .md trong repo. Markdown render bằng `python-markdown`
với extensions `tables` + `fenced_code` cho bảng và code block.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import SessionUser, require_user
from app.version import VERSION, version_string

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR.parent / "docs"

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()

# Mỗi entry: slug → (file, title, description, category).
# category: "methodology" (phương pháp luận) | "legal" (văn bản pháp lý).
# Whitelist — chỉ slug ở đây mới được render. Thêm tài liệu mới: thêm 1 entry.
PUBLIC_DOCS: dict[str, tuple[str, str, str, str]] = {
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
    "methodology": "Phương pháp luận",
    "legal": "Văn bản pháp lý",
}
CATEGORY_ORDER = ["methodology", "legal"]


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
            {"slug": slug, "title": title, "description": description}
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


@router.get("/tai-lieu/{slug}", response_class=HTMLResponse)
def render_doc(
    slug: str,
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    entry = PUBLIC_DOCS.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Không có tài liệu '{slug}'")
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
