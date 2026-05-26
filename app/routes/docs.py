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

# Map slug → (file, title). Whitelist các trang được công khai.
PUBLIC_DOCS: dict[str, tuple[str, str]] = {
    "scoring-methodology": (
        "scoring-methodology.md",
        "Phương pháp tính điểm rủi ro",
    ),
}


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


@router.get("/tai-lieu/{slug}", response_class=HTMLResponse)
def render_doc(
    slug: str,
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    entry = PUBLIC_DOCS.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Không có tài liệu '{slug}'")
    filename, title = entry
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
