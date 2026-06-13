"""Soạn check mở rộng (SQL/Python) từ ngôn ngữ tự nhiên — agentic tool-loop.

Port các phương pháp của BCQT-System để kết quả AI tốt hơn hẳn cách cũ (gọi 1 phát,
không grounding, không dry-run):

1. **Tool-use loop** — LLM tự khám phá schema + dữ liệu THẬT trước khi viết:
   get_table_schema, get_distinct_values, try_sql, lookup_glossary, submit_final_answer.
   Mọi tool read-only, scope theo (DN tham chiếu, năm) admin chọn.
2. **Deterministic oracle + retry** — validate (deny-list/shape) + dry-run thật; lỗi
   được phản hồi (gắn nhãn) cho LLM tự sửa qua nhiều lần.
3. **Self-review + plan** — LLM tự khai độ tin cậy + cách hiểu thay thế + các bước.
4. **Dynamic few-shot** — ví dụ động từ check đã lưu (Jaccard trên nl_prompt).

KHÔNG dùng fallback provider — fail thì báo lỗi rõ để admin biết (tránh downgrade thầm).
"""

# File template prompt — chứa ví dụ SQL/JSON dài cố ý; bỏ giới hạn độ dài dòng.
# ruff: noqa: E501

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.client import make_client
from app.ai.config import get_setting
from app.checks.sql_runner import (
    ALLOWED_SCOPES,
    ALLOWED_SUBJECT_TABLES,
    dry_run,
    select_in_savepoint,
    validate_check_definition,
    validate_sql_is_select_only,
)

log = logging.getLogger(__name__)


class SpecGenError(Exception):
    """Lỗi khi AI không soạn được check hợp lệ. Message dành cho hiển thị UI."""


# ---------------------------------------------------------------------------
# Schema metadata (cho tool + prompt)
# ---------------------------------------------------------------------------

# Cột nghiệp vụ cho mỗi bảng Tầng 1 + nhãn tiếng Việt (subject + metric).
_TABLE_META: dict[str, dict] = {
    "nvl_balances": {
        "label": "Mẫu 15 — cân đối NVL/NPL theo mã",
        "subject": [("material_code", "mã NVL"), ("material_name", "tên NVL"), ("unit", "ĐVT")],
        "metric": [
            ("opening_qty", "tồn đầu kỳ"), ("import_qty", "nhập trong kỳ"),
            ("reexport_qty", "tái xuất"), ("repurpose_qty", "chuyển mục đích sử dụng"),
            ("production_out_qty", "xuất sản xuất"), ("other_out_qty", "xuất khác"),
            ("closing_qty", "tồn cuối kỳ"),
        ],
    },
    "sp_balances": {
        "label": "Mẫu 15a — cân đối thành phẩm theo mã",
        "subject": [("product_code", "mã TP"), ("product_name", "tên TP"), ("unit", "ĐVT")],
        "metric": [
            ("opening_qty", "tồn đầu kỳ"), ("intake_qty", "nhập kho từ SX"),
            ("repurpose_qty", "chuyển mục đích sử dụng"), ("export_qty", "xuất khẩu"),
            ("other_out_qty", "xuất khác"), ("closing_qty", "tồn cuối kỳ"),
        ],
    },
    "declaration_lines": {
        "label": "BCCT — báo cáo hàng chi tiết (từng dòng tờ khai XNK)",
        "subject": [
            ("declaration_no", "số tờ khai"), ("declaration_date", "ngày tờ khai"),
            ("customs_code", "mã loại hình (E11/E15/E31/E33/E21/E23/E13...)"),
            ("item_code", "mã hàng (= mã NVL/SP DN khai)"), ("hs_code", "mã HS"),
            ("unit", "ĐVT"), ("currency", "loại tiền"), ("origin", "xuất xứ"),
            ("partner", "đối tác"),
        ],
        "metric": [
            ("quantity", "số lượng"), ("unit_price", "đơn giá"),
            ("value_foreign", "trị giá ngoại tệ"), ("value_total", "trị giá (VND)"),
            ("tax_total", "tổng thuế"),
        ],
    },
    "norms": {
        "label": "Mẫu 16 — định mức thực tế (mã SP → mã NVL)",
        "subject": [
            ("product_code", "mã SP"), ("material_code", "mã NVL"),
            ("product_unit", "ĐVT SP"), ("material_unit", "ĐVT NVL"),
        ],
        "metric": [("norm_qty", "định mức tiêu hao")],
    },
}

# Glossary nhỏ cho lookup_glossary.
_GLOSSARY: dict[str, str] = {
    "bcqt": "Báo cáo quyết toán — DN nộp định kỳ gồm Mẫu 15/15a/16.",
    "bcct": "Báo cáo hàng chi tiết — từng dòng tờ khai XNK (bảng declaration_lines).",
    "m15": "Mẫu 15 — cân đối nhập-xuất-tồn NVL/NPL (bảng nvl_balances).",
    "m15a": "Mẫu 15a — cân đối nhập-xuất-tồn thành phẩm (bảng sp_balances).",
    "m16": "Mẫu 16 — định mức thực tế (bảng norms).",
    "nvl": "Nguyên vật liệu / nguyên phụ liệu nhập để sản xuất.",
    "npl": "Nguyên phụ liệu — đồng nghĩa NVL trong ngữ cảnh BCQT.",
    "tp": "Thành phẩm — hàng DN sản xuất để xuất khẩu.",
    "định mức": "Lượng NVL tiêu hao để làm 1 đơn vị thành phẩm (Mẫu 16).",
    "tờ khai": "Tờ khai hải quan; số tờ khai = declaration_no (12 số).",
    "loại hình": "Mã loại hình XNK (customs_code): E11/E15 nhập SXXK, E31/E33 nhập NSXXK, "
                 "E21/E23 nhập gia công, E13 nhập tạo TSCĐ, B/E62 xuất...",
    "mã hs": "Mã phân loại hàng hoá quốc tế (8 số, AHTN) — KHÁC mã hàng của DN.",
    "chuyển mục đích sử dụng": "NVL nhập miễn thuế đem dùng việc khác → cần tờ khai A42.",
}


def _table_schema(table: str) -> dict:
    meta = _TABLE_META.get(table)
    if meta is None:
        return {"ok": False, "error": f"Bảng không hợp lệ: {table!r}. Cho phép: {sorted(_TABLE_META)}"}
    cols = [{"name": c, "vi": label, "role": "subject"} for c, label in meta["subject"]]
    cols += [{"name": c, "vi": label, "role": "metric"} for c, label in meta["metric"]]
    return {"ok": True, "table": table, "label": meta["label"], "columns": cols}


def _all_columns(table: str) -> set[str]:
    meta = _TABLE_META.get(table, {})
    return {c for c, _ in meta.get("subject", [])} | {c for c, _ in meta.get("metric", [])}


# ---------------------------------------------------------------------------
# Tools (read-only, scope theo DN tham chiếu + năm)
# ---------------------------------------------------------------------------

DEFAULT_TOOL_CAPS = {
    "get_table_schema": 6,
    "get_distinct_values": 5,
    "try_sql": 8,
    "lookup_glossary": 4,
    "submit_final_answer": 2,
}
DEFAULT_TOTAL_MAX = 18


class _ToolBudget:
    def __init__(self) -> None:
        self.caps = dict(DEFAULT_TOOL_CAPS)
        self.counts: dict[str, int] = {}
        self.trace: list[str] = []

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def charge(self, name: str) -> str | None:
        if name not in self.caps:
            return f"Tool không hợp lệ: {name!r}"
        if self.total >= DEFAULT_TOTAL_MAX:
            return f"Đã hết tổng lượt tool ({DEFAULT_TOTAL_MAX})"
        if self.counts.get(name, 0) >= self.caps[name]:
            return f"Hết lượt cho tool {name!r} ({self.caps[name]})"
        self.counts[name] = self.counts.get(name, 0) + 1
        self.trace.append(name)
        return None


def _tool_get_distinct_values(session, company_id, year, table, column, limit=20):
    if table not in _TABLE_META:
        return {"ok": False, "error": f"Bảng không hợp lệ: {table!r}"}
    if column not in _all_columns(table):
        return {"ok": False, "error": f"Cột {column!r} không có trong {table}"}
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 20
    # table/column đã whitelist → an toàn để nội suy định danh.
    sql = (
        f"SELECT DISTINCT {column} AS v FROM {table} "
        f"WHERE company_id = :company_id AND period_year = :period_year "
        f"AND {column} IS NOT NULL LIMIT {limit + 1}"
    )
    try:
        _cols, rows = select_in_savepoint(
            session, sql, {"company_id": company_id, "period_year": year}
        )
    except SQLAlchemyError as exc:
        return {"ok": False, "error": f"Lỗi SQL: {exc}"}
    values = [r["v"] for r in rows[:limit]]
    return {"ok": True, "table": table, "column": column, "values": values,
            "truncated": len(rows) > limit}


def _tool_try_sql(session, company_id, year, query, sample_limit=5):
    err = validate_sql_is_select_only(query)
    if err:
        return {"ok": False, "error": err}
    try:
        sample_limit = max(1, min(int(sample_limit), 20))
    except (TypeError, ValueError):
        sample_limit = 5
    try:
        cols, rows = select_in_savepoint(
            session, query, {"company_id": company_id, "period_year": year}
        )
    except SQLAlchemyError as exc:
        return {"ok": False, "error": f"Lỗi SQL: {exc}"}
    return {"ok": True, "columns": cols, "rows": rows[:sample_limit],
            "truncated": len(rows) > sample_limit}


def _tool_lookup_glossary(query: str):
    q = (query or "").lower().strip()
    matches = [
        {"term": k, "definition": v}
        for k, v in _GLOSSARY.items()
        if q and (q in k or k in q or q in v.lower())
    ][:5]
    return {"ok": True, "matches": matches}


TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "get_table_schema",
        "description": "Trả cột (tên + nhãn tiếng Việt + vai trò subject/metric) của 1 bảng. "
                       "Bảng hợp lệ: nvl_balances, sp_balances, declaration_lines, norms. "
                       "Gọi trước khi viết SQL để dùng đúng tên cột.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string"}}, "required": ["table"]}}},
    {"type": "function", "function": {
        "name": "get_distinct_values",
        "description": "Trả tối đa `limit` giá trị phân biệt của 1 cột (vd customs_code, unit) "
                       "trên DN tham chiếu — để hiểu dữ liệu enum thực tế.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string"}, "column": {"type": "string"},
            "limit": {"type": "integer"}}, "required": ["table", "column"]}}},
    {"type": "function", "function": {
        "name": "try_sql",
        "description": "Chạy thử 1 câu SELECT (read-only) trên DN tham chiếu, trả tối đa 5 dòng "
                       "mẫu hoặc lỗi. Dùng :company_id và :period_year làm tham số. Verify logic "
                       "WHERE/JOIN trước khi chốt.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "sample_limit": {"type": "integer"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "lookup_glossary",
        "description": "Tra cứu thuật ngữ BCQT/hải quan (BCCT, M15, định mức, loại hình...).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "submit_final_answer",
        "description": "Nộp check hoàn chỉnh (JSON payload). Sẽ được validate + dry-run trên dữ "
                       "liệu thật. Gọi đúng 1 lần khi đã chắc chắn.",
        "parameters": {"type": "object", "properties": {
            "payload": {"type": "object"}}, "required": ["payload"]}}},
]


def _dispatch_tool(session, company_id, year, name, args):
    if name == "get_table_schema":
        return _table_schema(args.get("table", ""))
    if name == "get_distinct_values":
        return _tool_get_distinct_values(
            session, company_id, year, args.get("table", ""), args.get("column", ""),
            args.get("limit", 20))
    if name == "try_sql":
        return _tool_try_sql(session, company_id, year, args.get("query", ""),
                             args.get("sample_limit", 5))
    if name == "lookup_glossary":
        return _tool_lookup_glossary(args.get("query", ""))
    if name == "submit_final_answer":
        payload = args.get("payload")
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload phải là JSON object"}
        return {"ok": True, "final": True, "payload": payload}
    return {"ok": False, "error": f"Tool không hợp lệ: {name!r}"}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_CONTRACT = """\
## Hợp đồng kết quả (payload truyền cho submit_final_answer)

Chọn `kind` đơn giản nhất:
  kind = "sql"    — 1 câu SELECT. Cho lọc/aggregate/join.
  kind = "python" — snippet `def run(conn, company_id, period_year)` trả list dict. Cho regex/nhiều bước.

Mỗi DÒNG kết quả = 1 PHÁT HIỆN (per-subject, vd 1 mã NVL sai). Các khoá:
  plan          — list 3-7 gạch đầu dòng mô tả bước đã làm (bảng nào, cột nào, edge case nào).
  analysis      — 1-3 câu lý giải: bảng/cột nào, điều kiện gì, edge case nào liên quan.
  slug_hint     — định danh kebab-case ngắn (không tiền tố).
  title         — tiêu đề tiếng Việt <= 60 ký tự.
  description   — 1 câu thuần Việt, KHÔNG tên cột/SQL — cán bộ đọc phải gật "đúng ý tôi".
  base_severity — "critical" | "warning" | "info".
  scope         — "nvl" | "tp" | "m16" (chọn mẫu số tính điểm: nvl cho check trên NVL/định mức
                  phía nhập, tp cho thành phẩm phía xuất, m16 cho định mức).
  subject_table — bảng Tầng 1 để truy nguồn: nvl_balances | sp_balances | declaration_lines | norms.
  subject_col   — cột định danh subject trong subject_table (vd material_code, product_code, item_code).
  kind          — "sql" | "python".
  sql_snippet   — BẮT BUỘC khi kind=="sql". SELECT trả ĐÚNG các cột theo thứ tự:
                      severity, subject_key, title, detail
                  severity là literal/biểu thức trong {critical, warning, info}.
                  subject_key = mã đối tượng (khớp subject_col). PHẢI lọc :company_id và :period_year.
  detail_query  — TUỲ CHỌN khi kind=="sql". 1 SELECT khác trả vài dòng NGUỒN khớp điều kiện
                  (kèm LIMIT 5) để cán bộ tự kiểm chứng. SELECT-only, dùng :company_id/:period_year.
  code_snippet  — BẮT BUỘC khi kind=="python". Định nghĩa run(conn, company_id, period_year);
                  conn.execute("SELECT ... WHERE company_id=? AND period_year=?", (company_id, period_year));
                  trả list dict khoá: severity, subject_key, title, detail. conn read-only.
  self_review   — BẮT BUỘC, object:
                    edge_cases_handled: list edge case đã xử lý (vd ["NULL", "TRIM khoảng trắng"]).
                    alternative_interpretation: 1 cách hiểu KHÁC hợp lý của yêu cầu (tiếng Việt);
                      "không có" chỉ khi yêu cầu thực sự rõ ràng.
                    confidence: "high" | "medium" | "low" — tự đánh giá thành thật. Yêu cầu ngắn/
                      mơ hồ thì medium/low là bình thường.

Ràng buộc SQL: CHỈ SELECT (không INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA/ATTACH).
Ràng buộc Python: chỉ có sẵn re/json/datetime/collections; không import/open/exec; conn chỉ SELECT.
"""

_DOMAIN = """\
## Phân biệt định danh (HAY NHẦM — đọc kỹ)

Trên dòng BCCT (declaration_lines) có nhiều định danh khác nhau:
  - declaration_no (số tờ khai): định danh 1 TỜ KHAI (12 số), 1 tờ khai nhiều dòng hàng.
  - hs_code (mã HS): phân loại LOẠI hàng hoá quốc tế (8 số). Nhiều mã DN cùng 1 HS.
  - item_code (mã hàng): mã NVL/SP do DN khai — khớp material_code (M15) / product_code (M15a/M16).
Khi yêu cầu nói "mã NVL", "mã hàng", "mã SP" → là item_code/material_code/product_code,
KHÔNG phải hs_code hay declaration_no.

Mã loại hình (customs_code): nhập SXXK E11/E15; nhập NSXXK E31/E33; nhập gia công E21/E23;
nhập tạo TSCĐ/MMTB E13; xuất khẩu B11/E62... Dùng get_distinct_values để xem mã thật của DN.

## Hiệu chỉnh độ tin cậy

Câu kiểu "X không có trong Y" / "X không khớp Y" thường mơ hồ giữa:
  (a) X có tồn tại ở Y không (kiểm tra hiện diện), và
  (b) X trên từng dòng có khớp giá trị đăng ký cho CÙNG mã ở Y không (nhất quán per-mã).
Chọn cách hợp lý nhất nhưng đặt confidence=medium và ghi cách còn lại vào alternative_interpretation.

## Edge case cần cân nhắc mỗi lần

  1. NULL — dữ liệu hải quan hay thiếu; dùng `col IS NULL` tường minh.
  2. Khoảng trắng — bọc TRIM() khi so sánh chuỗi mã/đơn vị.
  3. Hoa/thường — bọc UPPER()/LOWER() khi so định danh.
  4. Số thực sai số — dùng ngưỡng (vd ABS(x) > 0.01) thay vì = 0.
Ghi edge case đã xử lý vào self_review.edge_cases_handled.
"""

_EXAMPLE = """\
## Ví dụ payload (kind="sql")

{
  "plan": ["Bảng nvl_balances, cột closing_qty là tồn cuối", "Lọc closing_qty < -0.01 (sai số)",
           "subject = material_code", "Tồn âm là sai nghiêm trọng -> critical"],
  "analysis": "Tìm mã NVL có tồn cuối kỳ âm trên M15. Dùng ngưỡng -0.01 tránh sai số dấu phẩy.",
  "slug_hint": "ton-cuoi-nvl-am",
  "title": "Tồn cuối kỳ NVL âm",
  "description": "Các mã nguyên vật liệu có tồn kho cuối kỳ âm trên Mẫu 15.",
  "base_severity": "critical",
  "scope": "nvl",
  "subject_table": "nvl_balances",
  "subject_col": "material_code",
  "kind": "sql",
  "sql_snippet": "SELECT 'critical' AS severity, material_code AS subject_key, 'Tồn cuối âm: ' || material_code AS title, 'closing=' || closing_qty AS detail FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year AND closing_qty < -0.01",
  "detail_query": "SELECT material_code, closing_qty FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year AND closing_qty < -0.01 LIMIT 5",
  "self_review": {"edge_cases_handled": ["sai số dấu phẩy (ngưỡng -0.01)"],
                  "alternative_interpretation": "không có", "confidence": "high"}
}

Luôn truyền JSON trên qua arg `payload` của submit_final_answer. KHÔNG in JSON ra nội dung tin nhắn.
"""


def _schema_block() -> str:
    lines = ["## Bảng & cột được phép truy vấn\n"]
    for table, meta in _TABLE_META.items():
        subj = ", ".join(f"{c} ({v})" for c, v in meta["subject"])
        metr = ", ".join(f"{c} ({v})" for c, v in meta["metric"])
        lines.append(f"{table} — {meta['label']}\n  subject: {subj}\n  metric: {metr}")
    return "\n".join(lines)


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def _tokenize(text_: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text_ or "")}


def _few_shot_block(session: Session, nl_prompt: str, k: int = 3) -> str:
    """Ví dụ động: check đã lưu có nl_prompt gần nhất (Jaccard)."""
    from app.models.check_definition import CheckDefinition

    new_tokens = _tokenize(nl_prompt)
    if not new_tokens:
        return ""
    rows = session.query(
        CheckDefinition.nl_prompt, CheckDefinition.kind,
        CheckDefinition.sql_snippet, CheckDefinition.code_snippet,
    ).filter(CheckDefinition.nl_prompt.isnot(None)).limit(200).all()
    scored = []
    for prompt, kind, sql, code in rows:
        other = _tokenize(prompt)
        inter = len(new_tokens & other)
        if not other or inter == 0:
            continue
        score = inter / len(new_tokens | other)
        scored.append((score, prompt, kind, sql or code or ""))
    scored.sort(key=lambda t: t[0], reverse=True)
    if not scored:
        return ""
    block = ["\n## Check đã được duyệt trước đây (gần yêu cầu này nhất)\n"]
    for _s, prompt, kind, snippet in scored[:k]:
        block.append(f"Yêu cầu: {prompt}\nkind: {kind}\nSnippet:\n{snippet}\n")
    return "\n".join(block)


def _build_system_prompt(session: Session, nl_prompt: str) -> str:
    return (
        "Bạn là kỹ sư kiểm toán hải quan Việt Nam, chuyên viết kiểm tra dữ liệu BCQT "
        "(Mẫu 15/15a/16 + tờ khai BCCT) cho hệ thống Audit-HQ. Bạn viết MỘT kiểm tra mỗi lần, "
        "theo yêu cầu tiếng Việt của cán bộ.\n\n"
        "## Quy trình\n"
        "Có các tool read-only để khám phá DB DN tham chiếu trước khi viết:\n"
        "  get_table_schema, get_distinct_values, try_sql, lookup_glossary, submit_final_answer.\n"
        "Khuyến nghị: (1) xem schema bảng liên quan; (2) try_sql kiểm chứng WHERE/JOIN trên dữ "
        "liệu thật; (3) submit_final_answer khi chắc. Ngân sách tool có hạn — đừng gọi lại điều "
        "đã biết, đừng try_sql trùng câu.\n\n"
        f"{_schema_block()}\n\n{_CONTRACT}\n{_DOMAIN}\n{_EXAMPLE}"
        f"{_few_shot_block(session, nl_prompt)}"
    )


# ---------------------------------------------------------------------------
# Tool-loop draft
# ---------------------------------------------------------------------------

_MAX_TURNS = 16
_DEFAULT_MAX_RETRIES = 2
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _parse_tool_args(raw: str) -> tuple[dict, str | None]:
    """Parse khoan dung JSON arg của tool (vài endpoint phát object nối / có fence)."""
    if not raw or not raw.strip():
        return {}, None
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result, None
        return {}, f"arg phải là JSON object, gặp {type(result).__name__}"
    except json.JSONDecodeError:
        pass
    try:
        obj, _idx = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError as exc:
        return {}, f"{exc.msg} (dòng {exc.lineno} cột {exc.colno})"
    if not isinstance(obj, dict):
        return {}, f"arg phải là JSON object, gặp {type(obj).__name__}"
    return obj, None


def _serialize_assistant(msg) -> dict:
    return {
        "role": "assistant",
        "content": getattr(msg, "content", None) or "",
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in (msg.tool_calls or [])
        ],
    }


def _draft_once(
    session: Session, company_id: int, year: int, nl_prompt: str,
    *, feedback: str | None, model: str,
) -> dict:
    """1 lượt agentic loop → payload dict. Raise SpecGenError nếu hỏng."""
    client = make_client()
    # Authoring cần đủ token cho payload đầy đủ (plan + analysis + SQL + self_review).
    try:
        max_tokens = max(int(get_setting("max_tokens") or 0), 2048)
    except (TypeError, ValueError, KeyError):
        max_tokens = 2048

    user_content = f"Hãy nộp kết quả qua submit_final_answer.\n\nYêu cầu: {nl_prompt}"
    if feedback:
        user_content += f"\n\nLần trước bị oracle từ chối. Lý do: {feedback}"

    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt(session, nl_prompt)},
        {"role": "user", "content": user_content},
    ]
    budget = _ToolBudget()

    for turn in range(_MAX_TURNS):
        try:
            completion = client.chat.completions.create(
                model=model, messages=messages, tools=TOOL_DEFINITIONS,
                temperature=0.1, max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            raise SpecGenError(f"Gọi AI thất bại: {exc}") from exc

        msg = completion.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            content = (getattr(msg, "content", None) or "")[:200]
            raise SpecGenError(f"AI không gọi tool (turn {turn}): {content!r}")

        messages.append(_serialize_assistant(msg))
        any_budget_err = False
        for tc in tool_calls:
            args, perr = _parse_tool_args(tc.function.arguments or "{}")
            if perr is not None:
                result = {"ok": False, "error": f"JSON arg lỗi: {perr}. Phát 1 JSON object duy nhất."}
            else:
                berr = budget.charge(tc.function.name)
                if berr is not None:
                    result = {"ok": False, "error": berr}
                    any_budget_err = True
                else:
                    result = _dispatch_tool(session, company_id, year, tc.function.name, args)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
            if result.get("final"):
                payload = dict(result["payload"])
                payload["_trace"] = list(budget.trace)
                return payload

        if budget.total >= DEFAULT_TOTAL_MAX or any_budget_err:
            raise SpecGenError(
                f"Hết ngân sách tool (trace={budget.trace}) mà chưa nộp kết quả"
            )

    raise SpecGenError(f"Quá {_MAX_TURNS} lượt mà AI chưa nộp kết quả")


# ---------------------------------------------------------------------------
# Oracle + retry → DraftResult
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _slugify(text_: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", text_.strip().lower()).strip("-")
    return (t or "kiem-tra")[:40]


@dataclass
class DraftResult:
    """Kết quả soạn check (CHƯA lưu) + bằng chứng dry-run cho trang preview."""

    nl_prompt: str
    kind: str
    title: str
    description: str
    slug: str
    base_severity: str
    scope: str
    subject_table: str | None
    subject_col: str | None
    sql_snippet: str
    detail_query: str
    code_snippet: str
    analysis: str
    plan: list = field(default_factory=list)
    self_review: dict = field(default_factory=dict)
    sample_rows: list = field(default_factory=list)
    matched_rows: list = field(default_factory=list)
    matched_columns: list = field(default_factory=list)
    finding_count: int = 0
    ref_company_code: str = ""
    ref_year: int = 0


def draft_and_validate(
    session: Session, company_id: int, year: int, nl_prompt: str,
    *, ref_company_code: str = "", max_retries: int | None = None,
) -> DraftResult:
    """Soạn → validate (deny-list/shape) → dry-run thật trên (DN tham chiếu, năm).

    Lỗi mỗi lần được phản hồi (gắn nhãn) cho AI tự sửa, tối đa `max_retries`+1 lần.
    Raise SpecGenError nếu cạn lượt.
    """
    if not nl_prompt or not nl_prompt.strip():
        raise SpecGenError("Mô tả không được trống.")
    model = get_setting("model_deep")
    if not model:
        raise SpecGenError("Chưa cấu hình model_deep trong /admin/ai.")
    if max_retries is None:
        max_retries = _DEFAULT_MAX_RETRIES

    feedback: str | None = None
    last_error = "không rõ"

    for attempt in range(max_retries + 1):
        log.info("spec_gen draft attempt %d/%d", attempt + 1, max_retries + 1)
        payload = _draft_once(
            session, company_id, year, nl_prompt, feedback=feedback, model=model,
        )

        kind = (payload.get("kind") or "sql").strip().lower()
        title = (payload.get("title") or "").strip()
        sql = (payload.get("sql_snippet") or "").strip()
        code = (payload.get("code_snippet") or "").strip()
        detail_query = (payload.get("detail_query") or "").strip()
        scope = (payload.get("scope") or "").strip().lower()
        subject_table = (payload.get("subject_table") or "").strip() or None
        subject_col = (payload.get("subject_col") or "").strip() or None
        base_severity = (payload.get("base_severity") or "warning").strip().lower()
        self_review = payload.get("self_review") if isinstance(payload.get("self_review"), dict) else {}
        plan = payload.get("plan") if isinstance(payload.get("plan"), list) else []
        analysis = (payload.get("analysis") or "").strip()

        def _retry(reason: str) -> None:
            nonlocal feedback, last_error
            log.warning("spec_gen oracle reject: %s", reason)
            feedback = reason
            last_error = reason

        if not title:
            _retry("Thiếu 'title' không rỗng.")
            continue
        if scope not in ALLOWED_SCOPES:
            _retry(f"scope phải thuộc {sorted(ALLOWED_SCOPES)} (gặp {scope!r}).")
            continue
        if subject_table and subject_table not in ALLOWED_SUBJECT_TABLES:
            _retry(f"subject_table không hợp lệ: {subject_table!r}.")
            continue

        verr = validate_check_definition(
            kind=kind, sql=sql, code=code, subject_table=subject_table, scope=scope,
        )
        if verr:
            _retry(verr)
            continue

        dr = dry_run(
            session, kind=kind, sql=sql, code=code, detail_query=detail_query,
            company_id=company_id, year=year, subject_table=subject_table,
            subject_col=subject_col, default_severity=base_severity,
        )
        if not dr["ok"]:
            _retry(f"Dry-run lỗi: {dr['error']}")
            continue

        slug = (payload.get("slug_hint") or "").strip().lower()
        if not _SLUG_RE.match(slug):
            slug = _slugify(title)

        if base_severity not in ("critical", "warning", "info"):
            base_severity = "warning"
        return DraftResult(
            nl_prompt=nl_prompt, kind=kind, title=title[:120],
            description=(payload.get("description") or "").strip(), slug=slug,
            base_severity=base_severity,
            scope=scope, subject_table=subject_table, subject_col=subject_col,
            sql_snippet=sql if kind == "sql" else "",
            detail_query=detail_query if kind == "sql" else "",
            code_snippet=code if kind == "python" else "",
            analysis=analysis, plan=plan, self_review=self_review,
            sample_rows=dr["sample_rows"], matched_rows=dr["matched_rows"],
            matched_columns=dr["matched_columns"], finding_count=dr["count"],
            ref_company_code=ref_company_code, ref_year=year,
        )

    raise SpecGenError(f"AI không soạn được check hợp lệ sau {max_retries + 1} lần. Lỗi cuối: {last_error}")


__all__ = ["DraftResult", "SpecGenError", "draft_and_validate"]
