"""Nhận diện doanh nghiệp gắn với cuộc trò chuyện (ADR #20).

Nhãn DN LƯU trên `ai_conversations.company_id`, quyết định MỘT lần lúc tạo cuộc
theo chuỗi ưu tiên tường minh, rồi cố định. Suy lại lúc đọc là hướng đã loại: nó
hỏng khi trang seed không phải `/companies/...` và khi finding id không sống qua
một lần chạy lại kiểm tra.

Mọi kết quả nhận diện đi qua `can_access_company_id` — nhãn không được là đường
vòng để cuộc trò chuyện trỏ tới DN ngoài phạm vi phân công (ADR #14).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SessionUser
from app.models import AiConversation, Company, Finding
from app.scoping import can_access_company_id


def _lookup_company(db: Session, ident: str | None) -> Company | None:
    """Resolve DN theo slug HOẶC code — KHÔNG kiểm quyền, KHÔNG raise.

    Cùng thứ tự ưu tiên với `get_company_or_404` (slug trước vì URL người dùng
    dùng slug, code sau cho link nội bộ/AI cũ).
    """
    if not ident:
        return None
    company = db.scalar(select(Company).where(Company.slug == ident))
    if company is None:
        company = db.scalar(select(Company).where(Company.code == ident))
    return company


def _visible_company_by_ident(db: Session, ident: str | None, user: SessionUser) -> Company | None:
    """Như `_lookup_company` nhưng trả None khi DN nằm ngoài phạm vi phân công."""
    company = _lookup_company(db, ident)
    if company is None or not can_access_company_id(db, user, company.id):
        return None
    return company


def resolve_company_for_new_conversation(
    db: Session, user: SessionUser, page_context: dict | None
) -> int | None:
    """DN của cuộc MỚI — dừng ở khớp đầu tiên, None nếu không tín hiệu nào khớp.

    Thứ tự: DN cán bộ chọn trên giao diện (chip phạm vi) → DN của trang đang xem
    → DN của phát hiện đang xem → không gắn. Chỉ nhận tín hiệu TƯỜNG MINH: nhãn
    đi vào system prompt nên nhận diện sai đắt hơn nhãn trang trí.
    """
    ctx = page_context or {}

    # 1-2. Cán bộ chọn thẳng trên giao diện (thắng mọi suy đoán từ URL), rồi tới
    # DN của trang đang xem (`/companies/{slug}` → dn_code là slug hoặc code).
    #
    # Tín hiệu trỏ tới DN KHÔNG tồn tại (mã cũ, DN đã gỡ) không phải một khớp —
    # đi tiếp xuống nhánh sau. Tín hiệu trỏ tới DN CÓ tồn tại nhưng ngoài phạm vi
    # thì DỪNG hẳn: rơi tiếp xuống nhánh phát hiện sẽ dán cho cuộc một DN khác
    # hẳn DN mà ngữ cảnh vừa nêu.
    for ident in (ctx.get("scope_company_code"), ctx.get("dn_code")):
        company = _lookup_company(db, ident)
        if company is None:
            continue
        if not can_access_company_id(db, user, company.id):
            return None
        return company.id

    # 3. Phát hiện đang xem.
    finding_id = ctx.get("finding_id")
    try:
        finding_id = int(finding_id) if finding_id is not None else None
    except (TypeError, ValueError):
        finding_id = None
    if finding_id is not None:
        finding = db.get(Finding, finding_id)
        if finding is not None and can_access_company_id(db, user, finding.company_id):
            return finding.company_id

    return None


def late_assign_company(
    db: Session, conv: AiConversation, mentions: list[dict] | None, user: SessionUser
) -> bool:
    """Gán DN muộn cho cuộc CÒN TRỐNG khi lượt này nhắc ĐÚNG một `@DN`.

    Trả True nếu vừa gán. Từ hai DN trở lên → giữ trống: câu hỏi so sánh không
    thuộc về riêng DN nào, và đoán bừa sẽ neo mọi lượt sau vào DN chọn nhầm.
    KHÔNG gán từ tool call — tool call vô hình với cán bộ.
    """
    if conv.company_id is not None:
        return False
    codes = {m.get("code") for m in (mentions or []) if m.get("type") == "company" and m.get("code")}
    if len(codes) != 1:
        return False
    company = _visible_company_by_ident(db, next(iter(codes)), user)
    if company is None:
        return False
    conv.company_id = company.id
    return True
