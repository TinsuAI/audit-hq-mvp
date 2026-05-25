"""Tool definitions cho AI assistant — OpenAI function-calling schema.

Mỗi tool: schema export cho LLM + Python implementation đọc DB read-only.
KHÔNG có tool nào write (đổi finding status, xoá data...).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_BADGE, SPECS
from app.models import Company, DeclarationLine, Finding, Norm, NvlBalance, SpBalance

# Map tên bảng cho query_raw_data — alias ngắn → SQLA model + identifier code field.
_RAW_TABLES: dict[str, dict[str, Any]] = {
    "m15": {"model": NvlBalance, "code_field": "material_code", "label": "M15 — Cân đối NVL"},
    "m15a": {"model": SpBalance, "code_field": "product_code", "label": "M15a — Cân đối SP"},
    "m16": {"model": Norm, "code_field": "material_code", "label": "M16 — Định mức"},
    "bcct": {"model": DeclarationLine, "code_field": "item_code", "label": "BCCT — Tờ khai chi tiết"},
}

# Path tới đề án — repo audit-hq cùng cấp.
_PROPOSAL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "audit-hq" / "de-an-audit-hq.md"

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
    {
        "type": "function",
        "function": {
            "name": "query_raw_data",
            "description": (
                "Truy vấn dữ liệu Tầng 1 (M15 cân đối NVL, M15a cân đối SP, M16 định mức, BCCT tờ khai). "
                "Dùng khi user hỏi 'mã X-DL trong M15 có thông số gì', 'tờ khai số ABC có items nào', "
                "'định mức của SP-001 là bao nhiêu'. Trả về list rows (max 50). KHÔNG dùng để liệt kê "
                "tất cả dòng — nên có filter cụ thể bằng mã."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "enum": ["m15", "m15a", "m16", "bcct"],
                        "description": "Bảng nguồn.",
                    },
                    "company_code": {
                        "type": "string",
                        "description": "Mã DN. Bắt buộc.",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Năm kỳ báo cáo. Bắt buộc.",
                    },
                    "filter_field": {
                        "type": "string",
                        "description": (
                            "Tên cột để filter (vd material_code, product_code, item_code, "
                            "declaration_no, hs_code). Optional — bỏ thì trả về tất cả."
                        ),
                    },
                    "filter_value": {
                        "type": "string",
                        "description": "Giá trị filter (LIKE — match substring uppercase).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số dòng max (default 20, max 50).",
                        "default": 20,
                    },
                },
                "required": ["table", "company_code", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_check",
            "description": (
                "Trả về định nghĩa nghiệp vụ + mức độ + nhóm cho 1 mã check (C1.1..C7.x) "
                "hoặc combo (COMBO_FORGED_NORM, COMBO_HS_GAMING, COMBO_UNDECLARED_SOURCE, "
                "COMBO_ACCOUNTING_INCONSISTENT). Dùng khi user hỏi 'C2.3 là gì', "
                "'combo HS_GAMING nghĩa là gì'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_code": {
                        "type": "string",
                        "description": "Mã check hoặc combo (vd C2.3, COMBO_HS_GAMING).",
                    },
                },
                "required": ["check_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_companies",
            "description": (
                "Liệt kê tất cả DN có trong hệ thống với điểm rủi ro + count finding theo năm. "
                "Dùng khi user hỏi 'có những DN nào', 'top 3 DN rủi ro cao nhất', "
                "'DN nào sạch nhất'. KHÔNG có argument."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_legal_context",
            "description": (
                "Trả về cơ sở pháp lý §1.4 đề án (Luật Hải quan, TT 38/2015, TT 39/2018, "
                "TT 121/2025, QĐ 1357/QĐ-TCHQ, Luật QLT 2019, NĐ 13/2023). Dùng khi user hỏi "
                "'pháp lý nào liên quan', 'căn cứ nào để thực hiện kiểm tra này'. "
                "Optional topic keyword để filter (vd 'thuế', 'rủi ro', 'bảo mật')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Từ khoá filter (optional). Bỏ thì trả về toàn bộ §1.4.",
                    },
                },
                "required": [],
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


def _query_raw_data(
    db: Session,
    *,
    table: str,
    company_code: str,
    year: int,
    filter_field: str | None = None,
    filter_value: str | None = None,
    limit: int = 20,
) -> dict:
    config = _RAW_TABLES.get(table)
    if config is None:
        return {"error": f"Bảng không hợp lệ: {table}. Chọn m15/m15a/m16/bcct."}

    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}", "count": 0, "rows": []}

    model = config["model"]
    stmt = select(model).where(
        model.company_id == company.id,
        model.period_year == year,
    )
    if filter_field and filter_value:
        col = getattr(model, filter_field, None)
        if col is None:
            return {
                "error": f"Cột {filter_field!r} không có trong bảng {table}. "
                         f"Các cột hợp lệ: {[c.name for c in model.__table__.columns]}",
            }
        stmt = stmt.where(col.contains(filter_value))

    limit = max(1, min(int(limit), 50))
    stmt = stmt.order_by(getattr(model, config["code_field"])).limit(limit)
    rows = db.scalars(stmt).all()

    # Exclude noisy columns (id, company_id, source_file) trong response để tiết kiệm token.
    exclude = {"id", "company_id", "period_year", "source_file"}
    cols = [c.name for c in model.__table__.columns if c.name not in exclude]

    return {
        "table": table,
        "table_label": config["label"],
        "company_code": company.code,
        "year": year,
        "filter": {"field": filter_field, "value": filter_value} if filter_field else None,
        "count": len(rows),
        "columns": cols,
        "rows": [
            {c: getattr(r, c, None) for c in cols}
            for r in rows
        ],
    }


def _explain_check(db: Session, *, check_code: str) -> dict:
    code = check_code.strip().upper()
    spec = SPECS.get(code) or COMBO_SPECS.get(code)
    if spec is None:
        # Try lowercase variants để robust với input AI cảm tính.
        spec = SPECS.get(check_code) or COMBO_SPECS.get(check_code)
    if spec is None:
        return {
            "error": f"Không có check/combo nào tên {check_code!r}.",
            "available_check_codes": sorted(SPECS.keys()),
            "available_combo_codes": sorted(COMBO_SPECS.keys()),
        }

    is_combo = code in COMBO_SPECS or check_code in COMBO_SPECS
    if is_combo:
        return {
            "kind": "combo",
            "code": spec.code,
            "title": spec.title,
            "description": spec.description,
            "triggers": list(spec.triggers),
            "severity": "🔴 Nghiêm trọng (combo cộng +20 đ)",
        }
    return {
        "kind": "check",
        "code": spec.code,
        "group": spec.group,
        "title": spec.title,
        "description": spec.description,
        "default_severity": f"{SEVERITY_BADGE.get(spec.default_severity, '')} {spec.default_severity.value}",
        "enabled": spec.enabled,
    }


def _list_companies(db: Session) -> dict:
    """Tất cả DN + score + count finding per year."""
    companies = db.scalars(
        select(Company).order_by(Company.risk_score.desc(), Company.code)
    ).all()
    out = []
    for c in companies:
        # Aggregate count theo (year, severity) — 1 query nhỏ per DN, ổn với <10 DN.
        rows = db.execute(
            select(Finding.period_year, Finding.severity, func.count())
            .where(Finding.company_id == c.id)
            .group_by(Finding.period_year, Finding.severity)
        ).all()
        per_year: dict[int, dict[str, int]] = {}
        for year, sev, n in rows:
            per_year.setdefault(year, {})[sev] = n
        out.append({
            "code": c.code,
            "name": c.name,
            "tax_id": c.tax_id,
            "risk_score": c.risk_score,
            "findings_per_year": per_year,
        })
    return {"count": len(out), "companies": out}


@lru_cache(maxsize=1)
def _load_legal_section() -> str | None:
    """Đọc §1.4 đề án từ md (cache forever).

    None nếu file đề án không tồn tại (vd CI runner chỉ checkout audit-hq-mvp).
    """
    if not _PROPOSAL_PATH.exists():
        return None
    text = _PROPOSAL_PATH.read_text(encoding="utf-8")
    # Match từ "### 1.4" cho tới header tiếp theo (### 1.5 hoặc ## 2)
    m = re.search(r"(### 1\.4 .*?)(?=\n### |\n## )", text, re.DOTALL)
    if m is None:
        return None
    return m.group(1).strip()


def _get_legal_context(db: Session, *, topic: str | None = None) -> dict:
    text = _load_legal_section()
    if text is None:
        return {
            "error": "Không load được §1.4 đề án (file đề án không có ở môi trường này).",
            "fallback": "Các căn cứ chính: Luật Hải quan 2014, TT 38/2015/TT-BTC, TT 39/2018/TT-BTC, "
                        "QĐ 1357/QĐ-TCHQ, Luật QLT 2019, NĐ 13/2023/NĐ-CP.",
        }

    if topic:
        topic_lower = topic.strip().lower()
        matched_lines = [
            line for line in text.split("\n")
            if topic_lower in line.lower()
        ]
        if matched_lines:
            return {
                "topic": topic,
                "matched_count": len(matched_lines),
                "lines": matched_lines,
            }
        # Không match → trả full + flag
        return {
            "topic": topic,
            "matched_count": 0,
            "note": f"Không tìm thấy keyword {topic!r} trong §1.4 — trả về toàn bộ.",
            "full_section": text,
        }
    return {"full_section": text}


TOOL_REGISTRY: dict[str, Any] = {
    "search_findings": _search_findings,
    "get_finding": _get_finding,
    "query_raw_data": _query_raw_data,
    "explain_check": _explain_check,
    "list_companies": _list_companies,
    "get_legal_context": _get_legal_context,
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
