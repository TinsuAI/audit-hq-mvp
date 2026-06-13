"""Runner cho check mở rộng viết bằng SQL / Python tự do (read-only).

Thay cho DSL khai báo cũ (`dynamic_runner`). Một check chạy trên (company, year):

- ``kind='sql'``  — 1 câu SELECT trả đúng các cột ``severity, subject_key, title,
  detail`` (tuỳ chọn thêm ``evidence_json``). PHẢI lọc theo bind param
  ``:company_id`` và ``:period_year``. Mỗi dòng kết quả = 1 phát hiện (per-subject).
- ``kind='python'`` — snippet định nghĩa ``run(conn, company_id, period_year)`` trả
  list dict cùng khoá. Mở regex / nhiều truy vấn / thống kê.

Truy nguồn (CLAUDE.md — không hộp đen): mỗi finding tự dựng ``evidence_refs`` về
Tầng 1 từ ``subject_table`` + ``subject_col`` + ``subject_key`` của dòng (giống
``dynamic_runner._evidence_ref``), hoặc dùng ``evidence_json`` do check trả về.

An toàn (mô hình BCQT — đủ cho 1 admin tin cậy, KHÔNG phải sandbox cứng):
- SQL: deny-list từ khoá + bắt buộc SELECT (``validate_sql_is_select_only``),
  chạy qua bind param (không nối chuỗi).
- Python: ``__builtins__`` hạn chế (không ``__import__``/``open``/``exec``/``eval``),
  connection bọc read-only (mọi ``execute`` đều qua deny-list SELECT).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.finding import Finding

log = logging.getLogger(__name__)

VALID_SEVERITIES = {"critical", "warning", "info"}
REQUIRED_COLUMNS = ("severity", "subject_key", "title", "detail")
OPTIONAL_COLUMNS = ("evidence_json",)
ALLOWED_SUBJECT_TABLES = {"nvl_balances", "sp_balances", "declaration_lines", "norms"}
ALLOWED_SCOPES = {"nvl", "tp", "m16"}
MAX_FINDINGS = 5000  # chặn check lỗi sinh quá nhiều finding

_DENYLIST_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "begin", "commit",
    "rollback", "savepoint", "truncate",
}
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


class CheckRunError(Exception):
    """Lỗi khi chạy/validate check SQL/Python. Message dành cho hiển thị UI."""


def validate_sql_is_select_only(sql: str) -> str | None:
    """Trả message lỗi nếu SQL có thể ghi/đổi state, ngược lại None.

    Bỏ comment (``-- …`` và ``/* … */``) trước khi quét để từ khoá cấm giấu
    trong comment vẫn không lọt. Match theo token (word-boundary)."""
    stripped = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    tokens = {m.group(0).lower() for m in _WORD_RE.finditer(stripped)}
    hits = tokens & _DENYLIST_KEYWORDS
    if hits:
        return f"chứa từ khoá bị cấm: {', '.join(sorted(hits))}"
    if not re.search(r"\bselect\b", stripped, re.IGNORECASE):
        return "phải là câu SELECT"
    return None


def validate_check_definition(
    *, kind: str, sql: str | None, code: str | None,
    subject_table: str | None, scope: str | None,
) -> str | None:
    """Validate tĩnh trước khi chạy (dùng ở authoring oracle + lúc publish)."""
    kind = (kind or "").lower()
    if kind not in ("sql", "python"):
        return f"kind phải là 'sql' hoặc 'python' (gặp {kind!r})"
    if scope and scope not in ALLOWED_SCOPES:
        return f"scope không hợp lệ: {scope!r} (cho phép {sorted(ALLOWED_SCOPES)})"
    if subject_table and subject_table not in ALLOWED_SUBJECT_TABLES:
        return (
            f"subject_table không hợp lệ: {subject_table!r} "
            f"(cho phép {sorted(ALLOWED_SUBJECT_TABLES)})"
        )
    if kind == "sql":
        if not (sql and sql.strip()):
            return "kind='sql' cần sql_snippet không rỗng"
        deny = validate_sql_is_select_only(sql)
        if deny:
            return f"SQL bị chặn: {deny}"
        if ":company_id" not in sql:
            return "SQL phải lọc theo :company_id (tránh lẫn dữ liệu DN khác)"
        if ":period_year" not in sql:
            return "SQL phải lọc theo :period_year (phát hiện gắn với 1 kỳ)"
    else:
        if not (code and code.strip()):
            return "kind='python' cần code_snippet không rỗng"
        if "def run" not in code:
            return "Snippet Python phải định nghĩa hàm run(conn, company_id, period_year)"
    return None


# --- Python sandbox (port BCQT, hạn chế builtins) ---

_SAFE_BUILTINS = {
    "None": None, "True": True, "False": False,
    "bool": bool, "int": int, "float": float, "str": str, "bytes": bytes,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "frozenset": frozenset,
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "any": any, "all": all,
    "print": lambda *a, **kw: None,
    "isinstance": isinstance, "issubclass": issubclass,
    "hasattr": hasattr, "getattr": getattr,
    "repr": repr, "hash": hash,
    "Exception": Exception, "ValueError": ValueError, "KeyError": KeyError,
    "TypeError": TypeError, "IndexError": IndexError,
    # Thiếu (cố ý): __import__, exec, eval, compile, open, input, globals, locals.
}


class _ROConnection:
    """Bọc read-only connection truyền cho snippet Python — mọi execute qua SELECT-guard."""

    def __init__(self, raw_conn: sqlite3.Connection) -> None:
        self._raw = raw_conn

    def execute(self, sql, params=()):
        err = validate_sql_is_select_only(sql)
        if err:
            raise PermissionError(f"Chỉ cho phép SELECT trong check: {err}")
        cur = self._raw.execute(sql, params)
        cur.row_factory = sqlite3.Row
        return cur


def _raw_conn(session: Session) -> sqlite3.Connection:
    """Lấy DBAPI sqlite3 connection của session (cùng DB, in-memory lẫn file)."""
    return session.connection().connection


def _exec_python(code: str, conn: _ROConnection, company_id: int, year: int) -> list[dict]:
    import collections
    import datetime as _dt
    import json as _json
    import re as _re

    ns: dict = {
        "__builtins__": _SAFE_BUILTINS,
        "re": _re, "json": _json, "datetime": _dt, "collections": collections,
    }
    try:
        exec(code, ns)  # noqa: S102 — restricted builtins ở trên
    except Exception as exc:  # noqa: BLE001
        raise CheckRunError(f"Lỗi nạp Python: {exc}") from exc
    fn = ns.get("run")
    if not callable(fn):
        raise CheckRunError("Snippet phải định nghĩa hàm run(conn, company_id, period_year).")
    try:
        result = fn(conn, company_id, year)
    except PermissionError as exc:
        raise CheckRunError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise CheckRunError(f"Lỗi khi chạy run(): {exc}") from exc
    if not isinstance(result, list):
        raise CheckRunError("run() phải trả về list các dict.")
    return result


# --- Map dòng kết quả → Finding ---


def _build_evidence(
    row: dict, subject_table: str | None, subject_col: str | None,
    company_id: int, year: int,
) -> list[dict]:
    """Dựng evidence_refs về Tầng 1. Ưu tiên evidence_json của check; fallback subject."""
    ev_raw = row.get("evidence_json")
    if ev_raw:
        try:
            ev = json.loads(ev_raw) if isinstance(ev_raw, str) else ev_raw
            if isinstance(ev, dict):
                ev = [ev]
            if isinstance(ev, list):
                return [e for e in ev if isinstance(e, dict) and e.get("table")]
        except (json.JSONDecodeError, TypeError):
            pass
    subject_key = row.get("subject_key")
    if subject_table in ALLOWED_SUBJECT_TABLES and subject_col and subject_key is not None:
        return [{
            "table": subject_table,
            "filter": {
                "company_id": company_id,
                "period_year": year,
                subject_col: str(subject_key),
            },
        }]
    return []


def _rows_to_findings(
    rows: list[dict], *, code: str, default_severity: str,
    subject_table: str | None, subject_col: str | None,
    company_id: int, year: int,
) -> list[Finding]:
    findings: list[Finding] = []
    for row in rows[:MAX_FINDINGS]:
        sev = str(row.get("severity") or "").strip().lower()
        if sev not in VALID_SEVERITIES:
            sev = default_severity if default_severity in VALID_SEVERITIES else "warning"
        title = (row.get("title") or "").strip() or code
        detail = row.get("detail")
        subject_key = row.get("subject_key")
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code=code,
            severity=sev,
            subject_type=subject_col or "",
            subject_key=str(subject_key) if subject_key is not None else "",
            title=title,
            details={"detail": detail} if detail is not None else {},
            evidence_refs=_build_evidence(row, subject_table, subject_col, company_id, year),
        ))
    return findings


def select_in_savepoint(session: Session, sql: str, params: dict) -> tuple[list[str], list[dict]]:
    """Chạy 1 SELECT trong SAVEPOINT → (columns, rows).

    Quan trọng: lỗi SQL trong `session.execute` làm hỏng transaction của session
    (mọi truy vấn sau raise PendingRollbackError). Bọc trong begin_nested để lỗi
    chỉ rollback savepoint, session vẫn dùng được — 1 check lỗi không làm hỏng cả
    run / lần dry-run kế tiếp.
    """
    with session.begin_nested():
        result = session.execute(text(sql), params)
        cols = list(result.keys())
        rows = [dict(m) for m in result.mappings()]
    return cols, rows


def _run_sql_rows(session: Session, sql: str, company_id: int, year: int) -> list[dict]:
    deny = validate_sql_is_select_only(sql)
    if deny:
        raise CheckRunError(f"SQL bị chặn: {deny}")
    try:
        cols, rows = select_in_savepoint(
            session, sql, {"company_id": company_id, "period_year": year}
        )
    except SQLAlchemyError as exc:
        raise CheckRunError(f"Lỗi SQL: {exc}") from exc
    missing = [c for c in REQUIRED_COLUMNS if c not in set(cols)]
    if missing:
        raise CheckRunError(
            f"SELECT thiếu cột {missing}. Cần đúng các cột: {', '.join(REQUIRED_COLUMNS)}"
            f" (tuỳ chọn thêm evidence_json)."
        )
    return rows


# --- API công khai (chạy trong pipeline) ---


def run_check(definition, session: Session, company_id: int, year: int) -> list[Finding]:
    """Chạy 1 CheckDefinition (kind sql/python) → list[Finding]. Read-only."""
    kind = (definition.kind or "sql").lower()
    if kind == "python":
        conn = _ROConnection(_raw_conn(session))
        rows = _exec_python(definition.code_snippet or "", conn, company_id, year)
    else:
        rows = _run_sql_rows(session, definition.sql_snippet or "", company_id, year)
    return _rows_to_findings(
        rows,
        code=definition.code,
        default_severity=definition.default_severity or "warning",
        subject_table=definition.subject_table,
        subject_col=definition.subject_col,
        company_id=company_id,
        year=year,
    )


# --- Dry-run cho authoring / preview (không ghi DB) ---


def dry_run(
    session: Session, *, kind: str, sql: str | None = None, code: str | None = None,
    detail_query: str | None = None, company_id: int, year: int,
    subject_table: str | None = None, subject_col: str | None = None,
    default_severity: str = "warning", check_code: str = "X.preview",
) -> dict:
    """Chạy thử check trên (company, year) — trả sample findings + dòng nguồn khớp.

    Returns: {ok, sample_rows, matched_rows, matched_columns, count, error}.
    Dùng ở oracle của spec_gen + trang preview authoring.
    """
    kind = (kind or "sql").lower()
    try:
        if kind == "python":
            conn = _ROConnection(_raw_conn(session))
            rows = _exec_python(code or "", conn, company_id, year)
            if not isinstance(rows, list):
                return {"ok": False, "error": "run() phải trả list dict."}
            for r in rows[:50]:
                if not isinstance(r, dict):
                    return {"ok": False, "error": f"Phần tử không phải dict: {type(r).__name__}"}
                miss = [c for c in REQUIRED_COLUMNS if c not in r]
                if miss:
                    return {"ok": False, "error": f"dict thiếu khoá {miss}"}
        else:
            rows = _run_sql_rows(session, sql or "", company_id, year)
    except CheckRunError as exc:
        return {"ok": False, "error": str(exc)}

    findings = _rows_to_findings(
        rows, code=check_code, default_severity=default_severity,
        subject_table=subject_table, subject_col=subject_col,
        company_id=company_id, year=year,
    )
    sample = [
        {
            "severity": f.severity,
            "subject_key": f.subject_key,
            "title": f.title,
            "detail": (f.details or {}).get("detail"),
        }
        for f in findings[:10]
    ]

    matched_rows: list[dict] = []
    matched_columns: list[str] = []
    if kind == "sql" and detail_query and detail_query.strip():
        deny = validate_sql_is_select_only(detail_query)
        if deny is None:
            try:
                matched_columns, rows = select_in_savepoint(
                    session, detail_query, {"company_id": company_id, "period_year": year}
                )
                matched_rows = rows[:5]
            except SQLAlchemyError as exc:
                log.info("dry_run detail_query failed: %s", exc)

    return {
        "ok": True,
        "sample_rows": sample,
        "matched_rows": matched_rows,
        "matched_columns": matched_columns,
        "count": len(findings),
        "error": None,
    }


__all__ = [
    "ALLOWED_SCOPES",
    "ALLOWED_SUBJECT_TABLES",
    "CheckRunError",
    "REQUIRED_COLUMNS",
    "dry_run",
    "run_check",
    "validate_check_definition",
    "validate_sql_is_select_only",
]
