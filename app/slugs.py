"""Sinh URL slug từ tên DN (tiếng Việt) — định danh URL có nghĩa thay cho mã DN_xxx.

`code` (DN_xxx) vẫn là khoá lưu trữ nội bộ (thư mục file thô + lớp AI); `slug` chỉ
phục vụ URL + hiển thị. Slug ổn định sau khi tạo (không tự đổi khi sửa tên) để khỏi
gãy bookmark/link.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company

# Tiền tố pháp lý (đã fold dấu) — bỏ để slug ngắn gọn, dài nhất khớp trước.
_FOLDED_PREFIXES = (
    "cong ty tnhh mot thanh vien",
    "cong ty tnhh mtv",
    "cong ty tnhh",
    "cong ty co phan",
    "cong ty cp",
    "cong ty",
    "doanh nghiep tu nhan",
    "dntn",
    "tap doan",
)


def _fold(s: str) -> str:
    """Bỏ dấu tiếng Việt → ASCII (đ/Đ xử lý riêng trước khi NFD)."""
    s = s.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def slugify_name(name: str | None) -> str:
    """'Công ty TNHH Điện Tử Phương Đông (Demo)' → 'dien-tu-phuong-dong'."""
    raw = re.sub(r"\(.*?\)", " ", name or "")  # bỏ phần trong ngoặc, vd (Demo)
    folded = _fold(raw).lower()
    folded = re.sub(r"[^a-z0-9]+", " ", folded).strip()
    for p in _FOLDED_PREFIXES:
        if folded.startswith(p + " "):
            folded = folded[len(p):].strip()
            break
    slug = re.sub(r"\s+", "-", folded)
    return slug or "dn"


def unique_slug(db: Session, base: str, exclude_id: int | None = None) -> str:
    """Đảm bảo slug duy nhất; trùng thì nối -2, -3,… (bỏ qua chính DN exclude_id)."""
    candidate = base
    n = 1
    while True:
        existing = db.scalar(select(Company).where(Company.slug == candidate))
        if existing is None or existing.id == exclude_id:
            return candidate
        n += 1
        candidate = f"{base}-{n}"
