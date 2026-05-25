"""Tool definitions cho AI assistant — OpenAI function-calling schema.

Mỗi tool: schema export cho LLM + Python implementation đọc DB read-only.
KHÔNG có tool nào write (đổi finding status, xoá data...).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Finding

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_findings",
            "description": (
                "Tìm phát hiện (finding) trong DB theo filter. Dùng khi user hỏi "
                "'DN X có findings gì', 'năm Y có lỗi nào critical', 'check C2.3 fire ở đâu'. "
                "Trả về list compact: id, check_code, severity, subject_key, title, status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_code": {
                        "type": "string",
                        "description": "Mã DN (vd DN_001, DN_003). Bắt buộc.",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Năm kỳ báo cáo (vd 2024). Optional — bỏ thì lấy tất cả năm.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "warning", "info"],
                        "description": "Lọc theo mức. Optional.",
                    },
                    "check_code": {
                        "type": "string",
                        "description": "Lọc theo mã check (vd C2.3, C3.2, COMBO_HS_GAMING). Optional.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["new", "confirmed", "rejected", "noted"],
                        "description": "Lọc theo trạng thái cán bộ đã đánh dấu. Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số dòng tối đa (default 20, max 50).",
                        "default": 20,
                    },
                },
                "required": ["company_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_finding",
            "description": (
                "Lấy chi tiết 1 finding theo id: mô tả nghiệp vụ, evidence_refs (chứng cứ Tầng 1), "
                "subject_key, details JSON. Dùng khi user hỏi 'chi tiết finding 123', "
                "'phát hiện này dựa trên dữ liệu gì'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "finding_id": {
                        "type": "integer",
                        "description": "ID của finding (số nguyên).",
                    },
                },
                "required": ["finding_id"],
            },
        },
    },
]


# ───────────── Implementations ─────────────

def _search_findings(
    db: Session,
    *,
    company_code: str,
    year: int | None = None,
    severity: str | None = None,
    check_code: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict:
    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}", "count": 0, "findings": []}

    stmt = select(Finding).where(Finding.company_id == company.id)
    if year is not None:
        stmt = stmt.where(Finding.period_year == year)
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    if check_code:
        stmt = stmt.where(Finding.check_code == check_code)
    if status:
        stmt = stmt.where(Finding.status == status)

    limit = max(1, min(int(limit), 50))
    stmt = stmt.order_by(Finding.severity, Finding.check_code, Finding.id).limit(limit)
    rows = db.scalars(stmt).all()

    return {
        "company_code": company.code,
        "company_name": company.name,
        "company_risk_score": company.risk_score,
        "count": len(rows),
        "filters": {
            "year": year, "severity": severity, "check_code": check_code, "status": status,
        },
        "findings": [
            {
                "id": f.id,
                "check_code": f.check_code,
                "severity": f.severity,
                "period_year": f.period_year,
                "subject_key": f.subject_key,
                "title": f.title,
                "status": f.status,
            }
            for f in rows
        ],
    }


def _get_finding(db: Session, *, finding_id: int) -> dict:
    finding = db.get(Finding, finding_id)
    if finding is None:
        return {"error": f"Không tìm thấy finding #{finding_id}"}
    company = db.get(Company, finding.company_id)
    return {
        "id": finding.id,
        "check_code": finding.check_code,
        "severity": finding.severity,
        "period_year": finding.period_year,
        "subject_key": finding.subject_key,
        "title": finding.title,
        "status": finding.status,
        "notes": finding.notes,
        "details": finding.details,
        "evidence_refs": finding.evidence_refs,
        "company": {
            "code": company.code if company else None,
            "name": company.name if company else None,
        } if company else None,
    }


TOOL_REGISTRY: dict[str, Any] = {
    "search_findings": _search_findings,
    "get_finding": _get_finding,
}


def run_tool(name: str, args_json: str, db: Session) -> str:
    """Dispatcher: tên tool + args JSON string → kết quả JSON string.

    Bắt mọi exception trả về JSON error để tool loop không crash request.
    Truncate result > 4000 chars để không blow context window.
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Tool args không phải JSON hợp lệ: {e}"}, ensure_ascii=False)
    try:
        result = fn(db, **args)
    except TypeError as e:
        return json.dumps({"error": f"Sai signature: {e}"}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — show error back to LLM để nó tự xử
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)

    output = json.dumps(result, ensure_ascii=False, default=str)
    if len(output) > 4000:
        return json.dumps(
            {"truncated": True, "preview": output[:3800], "note": "Result > 4000 chars, đã cắt"},
            ensure_ascii=False,
        )
    return output
