"""SQL chỉ-đọc cho AI assistant — truy vấn linh hoạt trên VIEW có kiểm soát.

Cán bộ HQ hỏi câu mở (aggregate, top-N, group, cross-DN) → LLM sinh SQL →
chạy qua chính `db: Session` của request (KHÔNG mở connection riêng, để dùng
chung DB với prod WAL lẫn test in-memory).

3 lớp an toàn (DB chứa `users` password hash + `ai_settings` api_key secret):
1. Guard `validate_sql`: chỉ 1 câu SELECT/WITH; bảng phải ∈ allowlist view (`v_*`)
   hoặc CTE-name; denylist cứng bảng nhạy cảm; chặn keyword ghi/DDL/PRAGMA/ATTACH.
2. `PRAGMA query_only=ON` lúc chạy (chặn ghi ở tầng SQLite), reset OFF ở finally.
3. Bọc `LIMIT` ngoài cùng (cap cứng) + progress-handler timeout chặn query treo.
"""

from __future__ import annotations

import re
import sqlite3
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

# View whitelist — LLM chỉ được truy vấn các tên này (ngoài CTE tự định nghĩa).
ALLOWED_VIEWS: frozenset[str] = frozenset({
    "v_findings", "v_m15", "v_m15a", "v_m16", "v_bcct", "v_company_scores",
})

# Bảng nhạy cảm / nội bộ — reject cứng nếu xuất hiện ở BẤT KỲ đâu trong query
# (backstop cho trường hợp parse FROM/JOIN bỏ sót subquery hoặc comma-join).
_DENY_TABLES: frozenset[str] = frozenset({
    "users", "ai_settings", "ai_messages", "ai_conversations", "jobs",
    "app_settings", "check_definitions", "alembic_version",
    "sqlite_master", "sqlite_schema", "sqlite_temp_master",
})

# Keyword cấm — kể cả khi câu vẫn parse được như SELECT. KHÔNG đưa `replace`
# vào đây vì REPLACE() là hàm scalar hợp lệ của SQLite.
_DENY_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|"
    r"vacuum|reindex|truncate|grant|revoke|analyze)\b",
    re.IGNORECASE,
)

_DENY_TABLES_RE = re.compile(
    r"\b(" + "|".join(sorted(_DENY_TABLES)) + r")\b", re.IGNORECASE
)

# Identifier ở vị trí bảng: sau FROM / JOIN.
_TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
# CTE name: `WITH x AS (` / `, x AS (`.
_CTE_RE = re.compile(r"(?:\bwith\b|,)\s*([a-zA-Z_][\w]*)\s+as\s*\(", re.IGNORECASE)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_LIMIT_RE = re.compile(r"\blimit\b", re.IGNORECASE)

DEFAULT_ROW_CAP = 200
DEFAULT_TIMEOUT_MS = 2000

# Inner SELECT cho 6 view — join company_id → code, ẩn cột nội bộ. MỌI view đều
# phơi cột `company_code` để phân quyền theo DN (scoped temp view lọc trên cột này).
# Dùng dựng cả VIEW thật (admin, không giới hạn) lẫn TEMP VIEW scoped (officer).
_VIEW_SELECT: dict[str, str] = {
    "v_findings": """
        SELECT f.id AS finding_id, c.code AS company_code, f.period_year,
               f.check_code, f.severity, f.subject_type, f.subject_key,
               f.title, f.status, f.notes
        FROM findings f JOIN companies c ON c.id = f.company_id
    """,
    "v_m15": """
        SELECT c.code AS company_code, n.period_year, n.row_no,
               n.material_code, n.material_name, n.unit,
               n.opening_qty, n.import_qty, n.reexport_qty, n.repurpose_qty,
               n.production_out_qty, n.other_out_qty, n.closing_qty
        FROM nvl_balances n JOIN companies c ON c.id = n.company_id
    """,
    "v_m15a": """
        SELECT c.code AS company_code, s.period_year, s.row_no,
               s.product_code, s.product_name, s.unit,
               s.opening_qty, s.intake_qty, s.repurpose_qty,
               s.export_qty, s.other_out_qty, s.closing_qty
        FROM sp_balances s JOIN companies c ON c.id = s.company_id
    """,
    "v_m16": """
        SELECT c.code AS company_code, m.period_year,
               m.product_code, m.product_name, m.product_unit,
               m.material_code, m.material_name, m.material_unit,
               m.norm_qty, m.note
        FROM norms m JOIN companies c ON c.id = m.company_id
    """,
    "v_bcct": """
        SELECT c.code AS company_code, d.period_year, d.declaration_no,
               d.declaration_date, d.customs_code, d.line_no, d.item_code,
               d.item_name, d.hs_code, d.origin, d.quantity, d.unit,
               d.unit_price, d.currency, d.value_foreign, d.value_total,
               d.tax_total, d.partner, d.invoice_no
        FROM declaration_lines d JOIN companies c ON c.id = d.company_id
    """,
    "v_company_scores": """
        SELECT c.code AS company_code, c.name AS company_name, c.industry,
               c.risk_score AS overall_risk_score,
               cys.period_year, cys.score, cys.tier
        FROM companies c
        LEFT JOIN company_year_scores cys ON cys.company_id = c.id
    """,
}


class SqlGuardError(ValueError):
    """SQL bị guard từ chối — message tiếng Việt để trả thẳng cho LLM/cán bộ."""


def _is_sqlite(db: Session) -> bool:
    return db.bind is None or db.bind.dialect.name == "sqlite"


def ensure_views(db: Session) -> None:
    """Tạo 6 view thật (idempotent). Gọi đầu mỗi query — CREATE VIEW IF NOT EXISTS rẻ.

    Chỉ áp dụng cho SQLite (toàn bộ stack). Bỏ qua dialect khác.
    """
    if not _is_sqlite(db):
        return
    for name, sel in _VIEW_SELECT.items():
        db.execute(text(f"CREATE VIEW IF NOT EXISTS {name} AS {sel}"))


def _quoted_code_list(codes: set[str]) -> str | None:
    """`'DN_001', 'DN_003'` cho mệnh đề IN. None nếu rỗng (officer chưa được gán DN nào)."""
    if not codes:
        return None
    return ", ".join("'" + c.replace("'", "''") + "'" for c in sorted(codes))


def install_scoped_views(db: Session, allowed_codes: set[str]) -> None:
    """Tạo TEMP VIEW cùng tên 6 view, lọc `company_code IN (allowed)`.

    SQLite ưu tiên schema `temp` → câu SQL của officer tham chiếu `v_findings`…
    sẽ resolve vào temp view đã lọc (lọc TẠI NGUỒN, trước mọi aggregate — wrap
    LIMIT ngoài cùng không đủ an toàn cho COUNT/SUM). Set rỗng → `WHERE 0` (không
    dòng nào). Phải gọi TRƯỚC khi bật `PRAGMA query_only` (đây là DDL).
    """
    if not _is_sqlite(db):
        return
    inlist = _quoted_code_list(allowed_codes)
    where = "WHERE 0" if inlist is None else f"WHERE company_code IN ({inlist})"
    for name, sel in _VIEW_SELECT.items():
        db.execute(text(f"DROP VIEW IF EXISTS temp.{name}"))
        db.execute(text(f"CREATE TEMP VIEW {name} AS SELECT * FROM ({sel}) AS _s {where}"))


def drop_scoped_views(db: Session) -> None:
    """Gỡ TEMP VIEW scoped (gọi trong finally để không rò sang request sau)."""
    if not _is_sqlite(db):
        return
    for name in _VIEW_SELECT:
        db.execute(text(f"DROP VIEW IF EXISTS temp.{name}"))


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT_RE.sub(" ", _BLOCK_COMMENT_RE.sub(" ", sql)).strip()


def validate_sql(sql: str, row_cap: int = DEFAULT_ROW_CAP) -> tuple[str, str]:
    """Guard + chuẩn hoá. Trả `(display_sql, exec_sql)` hoặc raise SqlGuardError.

    `display_sql` = câu đã bỏ comment (để hiện cho cán bộ kiểm chứng).
    `exec_sql`    = câu bọc LIMIT ngoài cùng (cap cứng) để chạy.
    """
    if not sql or not sql.strip():
        raise SqlGuardError("Câu truy vấn trống.")

    cleaned = _strip_comments(sql).rstrip(";").strip()
    if not cleaned:
        raise SqlGuardError("Câu truy vấn trống sau khi bỏ chú thích.")

    # 1 câu duy nhất — không cho `;` nối nhiều lệnh.
    if ";" in cleaned:
        raise SqlGuardError("Chỉ cho phép một câu lệnh SELECT duy nhất (phát hiện ';').")

    low = cleaned.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise SqlGuardError("Chỉ cho phép câu bắt đầu bằng SELECT hoặc WITH.")

    if _DENY_KEYWORDS.search(cleaned):
        raise SqlGuardError(
            "Câu chứa từ khoá bị cấm (chỉ được đọc — không INSERT/UPDATE/DELETE/DDL/PRAGMA)."
        )

    # Backstop: bảng nhạy cảm xuất hiện ở bất kỳ đâu → reject ngay.
    deny = _DENY_TABLES_RE.search(cleaned)
    if deny:
        raise SqlGuardError(
            f"Không được truy vấn bảng {deny.group(1)!r}. "
            f"Chỉ dùng các view: {', '.join(sorted(ALLOWED_VIEWS))}."
        )

    # Mọi bảng ở vị trí FROM/JOIN phải ∈ allowlist view hoặc là CTE-name.
    cte_names = {m.lower() for m in _CTE_RE.findall(cleaned)}
    for ref in _TABLE_REF_RE.findall(cleaned):
        name = ref.lower()
        if name in cte_names or name in ALLOWED_VIEWS:
            continue
        raise SqlGuardError(
            f"Bảng/nguồn {ref!r} không được phép. "
            f"Chỉ dùng view: {', '.join(sorted(ALLOWED_VIEWS))} (hoặc CTE tự định nghĩa)."
        )

    cap = max(1, int(row_cap))
    # Bọc LIMIT ngoài cùng để cap cứng dù câu trong có LIMIT lớn hơn.
    exec_sql = f"SELECT * FROM (\n{cleaned}\n) AS _ahq_capped LIMIT {cap}"
    return cleaned, exec_sql


def _dbapi_connection(db: Session):
    sa_conn = db.connection().connection
    return (
        getattr(sa_conn, "dbapi_connection", None)
        or getattr(sa_conn, "driver_connection", None)
        or sa_conn
    )


def run_query(
    db: Session,
    sql: str,
    *,
    row_cap: int = DEFAULT_ROW_CAP,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    allowed_codes: set[str] | None = None,
) -> dict:
    """Chạy SQL chỉ-đọc an toàn. Trả dict cho tool (KHÔNG raise — gói lỗi vào `error`).

    `allowed_codes=None` → không giới hạn DN (admin). Set → officer: cài TEMP VIEW
    lọc theo DN được phân công trước khi chạy (xem `install_scoped_views`).
    """
    try:
        display_sql, exec_sql = validate_sql(sql, row_cap=row_cap)
    except SqlGuardError as e:
        return {"error": str(e), "sql": sql}

    ensure_views(db)
    scoped = allowed_codes is not None
    if scoped:
        install_scoped_views(db, allowed_codes)
    cap = max(1, int(row_cap))

    raw = _dbapi_connection(db)
    is_sqlite = isinstance(raw, sqlite3.Connection)
    deadline = time.monotonic() + max(0.05, timeout_ms / 1000.0)

    def _progress() -> int:
        return 1 if time.monotonic() > deadline else 0

    sa_conn = db.connection()
    if is_sqlite:
        sa_conn.exec_driver_sql("PRAGMA query_only=ON")
        raw.set_progress_handler(_progress, 2000)
    try:
        result = sa_conn.exec_driver_sql(exec_sql)
        columns = list(result.keys())
        fetched = result.fetchall()
        rows = [
            {col: (v if not hasattr(v, "isoformat") else v.isoformat())
             for col, v in zip(columns, r, strict=False)}
            for r in fetched
        ]
    except Exception as e:  # noqa: BLE001 — trả lỗi cho LLM tự diễn giải
        msg = str(e)
        if "interrupted" in msg.lower():
            msg = f"Truy vấn vượt {timeout_ms}ms — hãy thu hẹp bằng filter/LIMIT."
        return {"error": f"Lỗi chạy SQL: {msg}", "sql": display_sql}
    finally:
        if is_sqlite:
            raw.set_progress_handler(None, 2000)
            sa_conn.exec_driver_sql("PRAGMA query_only=OFF")
        if scoped:
            drop_scoped_views(db)

    return {
        "sql": display_sql,
        "columns": columns,
        "row_count": len(rows),
        "truncated": len(rows) >= cap,
        "rows": rows,
    }
