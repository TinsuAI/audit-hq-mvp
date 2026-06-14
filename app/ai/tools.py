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

from app.ai.config import get_setting
from app.ai.sql_tool import run_query
from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_BADGE, SEVERITY_LABEL_VI, SPECS
from app.models import (
    Company,
    CompanyYearScore,
    DeclarationLine,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.pipeline.export import _LEGAL_REFERENCES

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
                "Trả về `count` = TỔNG số khớp filter (đếm thật) + `findings` = tối đa `limit` "
                "dòng liệt kê. ĐẾM số phát hiện phải dùng `count`, KHÔNG đếm theo số dòng liệt kê."
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
    {
        "type": "function",
        "function": {
            "name": "query_sql",
            "description": (
                "Truy vấn SQL CHỈ-ĐỌC để tổng hợp/aggregate/đếm/top-N/group/cross-DN khi "
                "các tool khác không đủ. CHỈ được SELECT trên 6 view (xem schema ở system "
                "prompt): v_findings, v_m15, v_m15a, v_m16, v_bcct, v_company_scores — mọi "
                "view đều có cột company_code + period_year. KHÔNG truy vấn được bảng khác. "
                "BẮT BUỘC trình bày lại câu SQL đã chạy cho cán bộ kiểm chứng. Ví dụ: "
                "\"đếm finding theo mức của DN_003 năm 2024\" → SELECT severity, COUNT(*) "
                "FROM v_findings WHERE company_code='DN_003' AND period_year=2024 GROUP BY severity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": (
                            "Một câu SELECT (hoặc WITH...SELECT) duy nhất trên view v_*. "
                            "Không dấu ';', không INSERT/UPDATE/DELETE/DDL."
                        ),
                    },
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_excel",
            "description": (
                "Tạo link tải báo cáo Excel kiến nghị kiểm tra (7 sheet: tổng quan, phát hiện, "
                "chứng cứ M15/M15a/M16/BCCT, pháp lý) cho 1 DN + năm. Trả về download_url để "
                "cán bộ bấm tải. Dùng khi user nói 'xuất Excel', 'tải báo cáo', 'export báo cáo'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_code": {"type": "string", "description": "Mã DN. Bắt buộc."},
                    "year": {"type": "integer", "description": "Năm kỳ báo cáo. Bắt buộc."},
                },
                "required": ["company_code", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_check_run",
            "description": (
                "ĐỀ XUẤT chạy lại bộ kiểm tra cho 1 DN (1 năm cụ thể hoặc mọi năm). KHÔNG tự "
                "chạy — trả về đề xuất để cán bộ bấm nút xác nhận, vì hành động này thay đổi "
                "phát hiện + điểm rủi ro. Dùng khi user nói 'chạy kiểm tra', 'chạy lại check', "
                "'rà soát lại DN X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_code": {"type": "string", "description": "Mã DN. Bắt buộc."},
                    "year": {
                        "type": "integer",
                        "description": "Năm cụ thể. Bỏ trống = chạy mọi năm có dữ liệu (batch).",
                    },
                },
                "required": ["company_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": (
                "Gom toàn bộ dữ liệu để VIẾT báo cáo rủi ro 1 DN + năm trong MỘT lần gọi: "
                "thông tin DN, điểm + hạng, tổng hợp phát hiện theo nhóm/mức, tổ hợp rủi ro, "
                "phát hiện nghiêm trọng tiêu biểu, căn cứ pháp lý, link Excel. Dùng khi user "
                "nói 'viết báo cáo', 'soạn báo cáo', 'tóm tắt toàn diện'. Sau khi gọi, viết "
                "văn xuôi tiếng Việt formal theo template báo cáo, cite [finding:id]."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_code": {"type": "string", "description": "Mã DN. Bắt buộc."},
                    "year": {"type": "integer", "description": "Năm kỳ báo cáo. Bắt buộc."},
                },
                "required": ["company_code", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_score",
            "description": (
                "Trả về breakdown ĐIỂM RỦI RO thật của 1 DN + năm: điểm từng bài kiểm tra (0..10), "
                "mẫu số (độ phơi nhiễm), điểm tổ hợp, raw, max_raw. BẮT BUỘC gọi tool này khi "
                "user hỏi 'vì sao DN X năm Y có Z điểm' — điểm là RATE-BASED (không phải số "
                "finding × trọng số), phải giải thích từ breakdown này."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_code": {"type": "string", "description": "Mã DN. Bắt buộc."},
                    "year": {"type": "integer", "description": "Năm kỳ báo cáo. Bắt buộc."},
                },
                "required": ["company_code", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_query_excel",
            "description": (
                "Xuất Excel TÙY BIẾN từ một câu SQL — dùng khi cán bộ muốn tải kết quả một "
                "truy vấn phức tạp (vd cross-DN, lọc/tổng hợp đặc thù) mà báo cáo mặc định "
                "(export_excel) KHÔNG có. Truyền chính câu SELECT trên view v_* (cùng quy tắc "
                "như query_sql). File Excel chứa kết quả + câu SQL đã chạy (để truy nguồn). "
                "Trả download_url. KHÔNG dùng cho báo cáo kiến nghị mặc định 1 DN/năm — đó là export_excel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Câu SELECT/WITH trên view v_* (một câu duy nhất, chỉ đọc).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Tiêu đề báo cáo hiển thị trong file (optional).",
                    },
                },
                "required": ["sql"],
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
        return {"error": f"Không tìm thấy DN {company_code}", "count": 0, "returned": 0, "findings": []}

    conditions = [Finding.company_id == company.id]
    if year is not None:
        conditions.append(Finding.period_year == year)
    if severity:
        conditions.append(Finding.severity == severity)
    if check_code:
        conditions.append(Finding.check_code == check_code)
    if status:
        conditions.append(Finding.status == status)

    # `count` = TỔNG số phát hiện khớp filter (đếm thật, không bị limit).
    total = db.scalar(select(func.count()).select_from(Finding).where(*conditions)) or 0

    limit = max(1, min(int(limit), 50))
    rows = db.scalars(
        select(Finding).where(*conditions)
        .order_by(Finding.severity, Finding.check_code, Finding.id)
        .limit(limit)
    ).all()

    result = {
        "company_code": company.code,
        "company_name": company.name,
        "company_risk_score": company.risk_score,
        "count": total,            # tổng thật khớp filter
        "returned": len(rows),     # số dòng liệt kê bên dưới (≤ limit)
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
    if total > len(rows):
        result["note"] = (
            f"Tổng {total} phát hiện khớp filter, chỉ liệt kê {len(rows)} dòng đầu. "
            f"Số liệu đếm phải dùng `count`={total}, KHÔNG đếm theo số dòng liệt kê."
        )
    return result


def _get_finding(
    db: Session, *, finding_id: int, allowed_codes: set[str] | None = None
) -> dict:
    finding = db.get(Finding, finding_id)
    if finding is None:
        return {"error": f"Không tìm thấy finding #{finding_id}"}
    company = db.get(Company, finding.company_id)
    # Officer chỉ xem finding của DN được phân công — báo "không tìm thấy" để
    # không lộ sự tồn tại của finding ngoài phạm vi.
    if allowed_codes is not None and (company is None or company.code not in allowed_codes):
        return {"error": f"Không tìm thấy finding #{finding_id}"}
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
    conditions = [model.company_id == company.id, model.period_year == year]
    if filter_field and filter_value:
        col = getattr(model, filter_field, None)
        if col is None:
            return {
                "error": f"Cột {filter_field!r} không có trong bảng {table}. "
                         f"Các cột hợp lệ: {[c.name for c in model.__table__.columns]}",
            }
        conditions.append(col.contains(filter_value))

    total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    limit = max(1, min(int(limit), 50))
    rows = db.scalars(
        select(model).where(*conditions).order_by(getattr(model, config["code_field"])).limit(limit)
    ).all()

    # Exclude noisy columns (id, company_id, source_file) trong response để tiết kiệm token.
    exclude = {"id", "company_id", "period_year", "source_file"}
    cols = [c.name for c in model.__table__.columns if c.name not in exclude]

    result = {
        "table": table,
        "table_label": config["label"],
        "company_code": company.code,
        "year": year,
        "filter": {"field": filter_field, "value": filter_value} if filter_field else None,
        "count": total,          # tổng thật khớp filter
        "returned": len(rows),   # số dòng trả về (≤ limit)
        "columns": cols,
        "rows": [
            {c: getattr(r, c, None) for c in cols}
            for r in rows
        ],
    }
    if total > len(rows):
        result["note"] = (
            f"Tổng {total} dòng khớp, chỉ trả {len(rows)} dòng đầu. Để đếm chính xác dùng "
            "`count` hoặc query_sql COUNT(*); KHÔNG đếm theo số dòng trả về."
        )
    return result


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


def _list_companies(db: Session, *, allowed_codes: set[str] | None = None) -> dict:
    """DN + score + count finding per year (officer: chỉ DN được phân công)."""
    stmt = select(Company).order_by(Company.risk_score.desc(), Company.code)
    if allowed_codes is not None:
        stmt = stmt.where(Company.code.in_(allowed_codes))
    companies = db.scalars(stmt).all()
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


def _query_sql(db: Session, *, sql: str, allowed_codes: set[str] | None = None) -> dict:
    """SQL chỉ-đọc trên view có kiểm soát (xem app/ai/sql_tool).

    `allowed_codes` (officer) → run_query cài TEMP VIEW lọc theo DN được phân công.
    """
    return run_query(
        db, sql,
        row_cap=int(get_setting("sql_row_cap")),
        timeout_ms=int(get_setting("sql_timeout_ms")),
        allowed_codes=allowed_codes,
    )


def _export_excel(db: Session, *, company_code: str, year: int) -> dict:
    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}"}
    count = db.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.company_id == company.id, Finding.period_year == year)
    ) or 0
    return {
        "company_code": company.code,
        "company_name": company.name,
        "year": year,
        "findings_count": count,
        "download_url": f"/companies/{company.code}/export?year={year}",
        "filename": f"audit-hq_{company.code}_{year}_kien-nghi-kiem-tra.xlsx",
        "note": (
            "Trình link download_url cho cán bộ bấm tải. File Excel 7 sheet: tổng quan, "
            "phát hiện, chứng cứ M15/M15a/M16/BCCT, pháp lý."
        ),
    }


def _propose_check_run(db: Session, *, company_code: str, year: int | None = None) -> dict:
    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}"}
    scope = f"năm {year}" if year else "mọi năm có dữ liệu"
    return {
        "_ui_action": "run_checks",
        "company_code": company.code,
        "company_name": company.name,
        "year": year,
        "label": f"Chạy kiểm tra {company.code} ({scope})",
        "note": (
            "Đây là ĐỀ XUẤT — chưa chạy. Hành động này chạy lại bộ kiểm tra, thay đổi phát "
            "hiện + điểm rủi ro. Cán bộ phải bấm nút xác nhận trên giao diện để thực hiện."
        ),
    }


def _generate_report(db: Session, *, company_code: str, year: int) -> dict:
    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}"}

    findings = db.scalars(
        select(Finding)
        .where(Finding.company_id == company.id, Finding.period_year == year)
        .order_by(Finding.severity, Finding.check_code, Finding.id)
    ).all()

    sev_totals = {"critical": 0, "warning": 0, "info": 0}
    by_check: dict[str, int] = {}
    by_group: dict[int, dict[str, int]] = {}
    combos: list[dict] = []
    top_findings: list[dict] = []
    for f in findings:
        if f.severity in sev_totals:
            sev_totals[f.severity] += 1
        by_check[f.check_code] = by_check.get(f.check_code, 0) + 1
        if f.check_code.startswith("COMBO_"):
            combos.append({
                "code": f.check_code,
                "title": f.title,
                "severity": SEVERITY_LABEL_VI.get(f.severity, f.severity),
                "subject_key": f.subject_key,
            })
            continue
        spec = SPECS.get(f.check_code)
        g = spec.group if spec else 0
        by_group.setdefault(g, {"critical": 0, "warning": 0, "info": 0})
        if f.severity in by_group[g]:
            by_group[g][f.severity] += 1
        if f.severity in ("critical", "warning") and len(top_findings) < 15:
            top_findings.append({
                "finding_id": f.id,
                "check_code": f.check_code,
                "severity": SEVERITY_LABEL_VI.get(f.severity, f.severity),
                "subject_key": f.subject_key,
                "title": f.title,
            })

    cys = db.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company.id,
            CompanyYearScore.period_year == year,
        )
    )

    return {
        "company": {
            "code": company.code,
            "name": company.name,
            "tax_id": company.tax_id,
            "industry": company.industry,
        },
        "year": year,
        "score": cys.score if cys else None,
        "tier": cys.tier if cys else None,
        "overall_risk_score": company.risk_score,
        "total_findings": len(findings),
        "severity_totals": sev_totals,
        "findings_by_group": by_group,
        "findings_by_check": by_check,
        "combos_fired": combos,
        "top_findings": top_findings,
        "legal_references": [
            {"ref": ref, "desc": desc} for ref, desc in _LEGAL_REFERENCES[:3]
        ],
        "download_url": f"/companies/{company.code}/export?year={year}",
        "note": (
            "Viết báo cáo văn xuôi tiếng Việt formal theo template (Tổng quan DN · Điểm rủi "
            "ro · Phát hiện theo nhóm · Tổ hợp rủi ro · Kiến nghị · Căn cứ pháp lý). Cite "
            "[finding:id] cho phát hiện cụ thể. Nêu rõ đây là chỉ số rủi ro dữ liệu, không "
            "phải kết luận vi phạm."
        ),
    }


def _explain_score(db: Session, *, company_code: str, year: int) -> dict:
    company = db.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        return {"error": f"Không tìm thấy DN {company_code}"}
    cys = db.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company.id,
            CompanyYearScore.period_year == year,
        )
    )
    if cys is None:
        return {
            "error": f"Chưa có điểm cho {company_code} năm {year} "
                     "(có thể chưa chạy kiểm tra cho năm này).",
        }
    from app.checks.scoring import COMBO_BONUS, MAX_RULE_SCORE

    bd = cys.breakdown or {}
    max_raw = bd.get("max_raw")
    # Số bài kiểm tra trong phạm vi tại thời điểm tính điểm này: max_raw = n_rules×10 + 20.
    n_rules = (
        int(round((max_raw - COMBO_BONUS) / MAX_RULE_SCORE))
        if max_raw else None
    )
    return {
        "company_code": company.code,
        "year": year,
        "score": cys.score,
        "tier": cys.tier,
        "raw": bd.get("raw"),
        "max_raw": max_raw,
        "n_rules": n_rules,                          # số bài kiểm tra (mẫu số của max_raw)
        "rule_scores": bd.get("rule_scores"),       # {check_code: điểm 0..10 (đã bão hoà)}
        "combo_bonus": bd.get("combo_bonus"),
        "denominators": bd.get("denominators"),     # mẫu số {nvl, tp, m16}
        "formula": (
            f"score = round(1000 × raw / max_raw); max_raw = n_rules×10 + 20 "
            f"(= {n_rules}×10 + 20 = {max_raw}). raw = Σ(điểm từng bài kiểm tra ≤10) + combo_bonus. "
            "Mỗi điểm bài = min(1, Σtrọng_số_finding/(10×mẫu_số)) × 10 → KỊCH KHUNG ở 10."
        ),
        "note": (
            "Giải thích điểm DỰA TRÊN rule_scores + denominators này. Nêu bài kiểm tra nào đã "
            "kịch khung (đạt 10) và tỷ lệ so với mẫu số. TUYỆT ĐỐI không tính 'số finding × trọng số'."
        ),
    }


def _export_query_excel(db: Session, *, sql: str, title: str | None = None) -> dict:
    """Trả link tải Excel tùy biến từ SQL. Validate guard sớm để báo lỗi ngay cho LLM."""
    from urllib.parse import quote

    from app.ai.sql_tool import SqlGuardError, validate_sql

    try:
        validate_sql(sql, row_cap=int(get_setting("sql_export_row_cap")))
    except SqlGuardError as e:
        return {"error": str(e), "sql": sql}

    qs = "sql=" + quote(sql)
    if title:
        qs += "&title=" + quote(title)
    return {
        "download_url": f"/api/chat/export-query?{qs}",
        "filename": "audit-hq_truy-van-tuy-bien.xlsx",
        "title": title,
        "sql": sql,
        "note": (
            "Trình link download_url cho cán bộ bấm tải. File Excel chứa kết quả truy vấn + "
            "câu SQL đã chạy để truy nguồn."
        ),
    }


TOOL_REGISTRY: dict[str, Any] = {
    "search_findings": _search_findings,
    "get_finding": _get_finding,
    "query_raw_data": _query_raw_data,
    "explain_check": _explain_check,
    "list_companies": _list_companies,
    "get_legal_context": _get_legal_context,
    "query_sql": _query_sql,
    "export_excel": _export_excel,
    "propose_check_run": _propose_check_run,
    "generate_report": _generate_report,
    "explain_score": _explain_score,
    "export_query_excel": _export_query_excel,
}

# Tool gated theo config flag — ẩn khỏi schema gửi LLM khi admin tắt.
_GATED_TOOLS: dict[str, str] = {
    "query_sql": "sql_tool_enabled",
    "export_query_excel": "sql_tool_enabled",
    "propose_check_run": "action_tools_enabled",
}


def get_tool_schemas() -> list[dict]:
    """Schema tool gửi cho LLM, đã lọc theo config flag runtime."""
    out = []
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        flag = _GATED_TOOLS.get(name)
        if flag is not None and not get_setting(flag):
            continue
        out.append(schema)
    return out


# Tool nhận `company_code` → chặn cứng nếu DN ngoài phạm vi officer (báo "không
# tìm thấy" để không lộ sự tồn tại). Các tool còn lại lọc nội bộ qua allowed_codes.
_GUARD_COMPANY_CODE = frozenset({
    "search_findings", "query_raw_data", "export_excel",
    "propose_check_run", "generate_report", "explain_score",
})
# Tool tự lọc theo allowed_codes (truyền vào implementation).
_INJECT_ALLOWED = frozenset({"list_companies", "get_finding", "query_sql"})


def run_tool(
    name: str, args_json: str, db: Session, allowed_codes: set[str] | None = None
) -> str:
    """Dispatcher: tên tool + args JSON string → kết quả JSON string.

    `allowed_codes=None` → admin (không giới hạn DN). Set → officer: chặn/lọc theo
    DN được phân công (cùng ranh giới với UI). Bắt mọi exception trả JSON error để
    tool loop không crash request.
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    if args_json and args_json.strip():
        try:
            # raw_decode: khoan dung với args bị nối '{...}{...}' (Gemini phát call song
            # song) — lấy object JSON đầu tiên thay vì lỗi "Extra data".
            args, _ = json.JSONDecoder().raw_decode(args_json.strip())
        except (json.JSONDecodeError, ValueError) as e:
            return json.dumps(
                {"error": f"Tool args không phải JSON hợp lệ: {e}"}, ensure_ascii=False
            )
        if not isinstance(args, dict):
            return json.dumps({"error": "Tool args phải là object JSON."}, ensure_ascii=False)
    else:
        args = {}

    # Phân quyền theo DN — bỏ key client tự gửi (chống widen scope), rồi enforce.
    args.pop("allowed_codes", None)
    if allowed_codes is not None:
        if name in _GUARD_COMPANY_CODE:
            code = args.get("company_code")
            if code and code not in allowed_codes:
                return json.dumps(
                    {"error": f"Không tìm thấy DN {code}"}, ensure_ascii=False
                )
        if name in _INJECT_ALLOWED:
            args["allowed_codes"] = allowed_codes

    try:
        result = fn(db, **args)
    except TypeError as e:
        return json.dumps({"error": f"Sai signature: {e}"}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — show error back to LLM để nó tự xử
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)

    output = json.dumps(result, ensure_ascii=False, default=str)
    max_chars = 8000
    if len(output) > max_chars:
        # Kết quả dạng {rows: [...]} (query_sql/query_raw_data): cắt bớt DÒNG, giữ
        # cấu trúc + câu SQL để FE render + LLM dùng tiếp, thay vì băm thành preview.
        if isinstance(result, dict) and isinstance(result.get("rows"), list) and result["rows"]:
            rows = result["rows"]
            while rows and len(json.dumps(result, ensure_ascii=False, default=str)) > max_chars:
                del rows[-max(1, len(rows) // 4):]
                result["truncated"] = True
                result["note"] = (
                    f"Kết quả lớn — đã cắt còn {len(rows)} dòng đầu. "
                    "Hãy thu hẹp bằng filter hoặc aggregate (COUNT/SUM/GROUP BY)."
                )
            output = json.dumps(result, ensure_ascii=False, default=str)
        if len(output) > max_chars:
            return json.dumps(
                {"truncated": True, "preview": output[:max_chars - 200],
                 "note": "Result quá lớn, đã cắt"},
                ensure_ascii=False,
            )
    return output
