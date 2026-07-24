"""Nhật ký truy cập — ghi sự kiện egress dữ liệu + hành động trên DN.

Chỉ ghi sự kiện nhạy cảm (tải file, xuất Excel, chạy kiểm tra), KHÔNG ghi mọi
lượt xem trang. Lỗi ghi log KHÔNG được làm hỏng request chính.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AccessEvent

log = logging.getLogger(__name__)

# Hành động chuẩn hoá (để lọc/thống kê nhất quán).
ACTION_DOWNLOAD = "download"          # tải file gốc
ACTION_EXPORT = "export"              # xuất báo cáo Excel 1 DN/năm
ACTION_EXPORT_QUERY = "export_query"  # xuất Excel từ SQL tuỳ biến
ACTION_RUN_CHECKS = "run_checks"      # chạy/kích hoạt bộ kiểm tra
ACTION_AI_OVERVIEW = "ai_overview"    # sinh AI tổng quan 1 test (gọi LLM tính tiền)

ACTION_LABEL_VI = {
    ACTION_DOWNLOAD: "Tải file",
    ACTION_EXPORT: "Xuất báo cáo",
    ACTION_EXPORT_QUERY: "Xuất truy vấn",
    ACTION_RUN_CHECKS: "Chạy kiểm tra",
    ACTION_AI_OVERVIEW: "Sinh AI tổng quan",
}


def log_access(
    db: Session,
    *,
    username: str,
    action: str,
    company_code: str | None = None,
    detail: str | None = None,
) -> None:
    """Ghi 1 sự kiện truy cập (tự commit). Nuốt lỗi để không làm hỏng request."""
    try:
        db.add(AccessEvent(
            username=username, action=action,
            company_code=company_code,
            detail=(detail[:500] if detail else None),
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — audit là phụ trợ, không được chặn nghiệp vụ
        log.exception("log_access failed (action=%s company=%s)", action, company_code)
        db.rollback()
