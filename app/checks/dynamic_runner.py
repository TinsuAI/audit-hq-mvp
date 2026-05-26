"""DynamicCheckRunner — chạy check định nghĩa bằng DSL khai báo (không exec code).

5 kind hỗ trợ:
  threshold_compare   — so sánh giá trị 1 cột với ngưỡng
  presence_check      — tìm key tồn tại ở bảng A không có ở bảng B (hoặc ngược)
  aggregate_threshold — group-by + agg rồi so sánh với ngưỡng
  cross_table_match   — so sánh metric giữa 2 bảng (diff%)
  ratio_threshold     — tỷ lệ 2 cột so với ngưỡng

Bảo mật:
  - Tên bảng và cột phải qua WHITELIST — không trust bất kỳ string nào từ DB.
  - Không dùng eval()/exec(). Không nối chuỗi SQL.
  - Filter dạng {"col__op": value} — parse explicit, không eval expression.
  - SQL build qua SQLAlchemy Core với param binding.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finding import Finding

# ---------------------------------------------------------------------------
# Whitelist tables + columns
# ---------------------------------------------------------------------------

# Các bảng được phép truy cập từ dynamic check.
_ALLOWED_TABLES: set[str] = {
    "nvl_balances",
    "sp_balances",
    "declaration_lines",
    "norms",
}

# Cột số cho từng bảng (có thể là metric/numerator/denominator).
_NUMERIC_COLS: dict[str, set[str]] = {
    "nvl_balances": {
        "opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
        "production_out_qty", "other_out_qty", "closing_qty",
    },
    "sp_balances": {
        "opening_qty", "intake_qty", "repurpose_qty", "export_qty",
        "other_out_qty", "closing_qty",
    },
    "declaration_lines": {
        "quantity", "unit_price", "value_foreign", "value_total",
        "tax_total",
    },
    "norms": {
        "norm_qty",
    },
}

# Cột chuỗi cho từng bảng (có thể là subject/join key).
_STRING_COLS: dict[str, set[str]] = {
    "nvl_balances": {"material_code", "material_name", "unit"},
    "sp_balances": {"product_code", "product_name", "unit"},
    "declaration_lines": {
        "declaration_no", "customs_code", "item_code", "hs_code",
        "unit", "currency", "origin", "partner",
    },
    "norms": {"product_code", "material_code", "product_unit", "material_unit"},
}

_ALL_COLS: dict[str, set[str]] = {
    t: (_NUMERIC_COLS.get(t, set()) | _STRING_COLS.get(t, set()))
    for t in _ALLOWED_TABLES
}

_ALLOWED_AGG_FNS: set[str] = {"sum", "count", "avg", "max", "min"}

_ALLOWED_FILTER_OPS: set[str] = {"gt", "gte", "lt", "lte", "eq", "ne", "in", "like"}

_ALLOWED_THRESHOLD_OPS: set[str] = {"gt", "gte", "lt", "lte", "eq"}


class SpecValidationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_model(table: str):
    """Trả về SQLAlchemy model class cho tên bảng đã whitelist."""
    from app.models.bcqt import Norm, NvlBalance, SpBalance
    from app.models.declaration import DeclarationLine

    return {
        "nvl_balances": NvlBalance,
        "sp_balances": SpBalance,
        "declaration_lines": DeclarationLine,
        "norms": Norm,
    }[table]


def _get_col(model, col_name: str, table: str, col_type: str = "any"):
    """Trả về SQLAlchemy column attribute sau khi verify whitelist."""
    allowed = _NUMERIC_COLS[table] if col_type == "numeric" else _ALL_COLS[table]
    if col_name not in allowed:
        raise SpecValidationError(
            f"col '{col_name}' không hợp lệ với bảng '{table}'. Cho phép: {sorted(allowed)}"
        )
    return getattr(model, col_name)


def _apply_filters(query, model, table: str, filters: dict[str, Any]):
    """Áp dụng dict filter vào SQLAlchemy query. An toàn — không eval chuỗi."""
    for key, val in filters.items():
        parts = key.rsplit("__", 1)
        if len(parts) == 1:
            col_name, op = parts[0], "eq"
        else:
            col_name, op = parts
        if op not in _ALLOWED_FILTER_OPS:
            raise SpecValidationError(f"filter op '{op}' không hợp lệ")
        col = _get_col(model, col_name, table)
        if op == "gt":
            query = query.where(col > val)
        elif op == "gte":
            query = query.where(col >= val)
        elif op == "lt":
            query = query.where(col < val)
        elif op == "lte":
            query = query.where(col <= val)
        elif op == "eq":
            query = query.where(col == val)
        elif op == "ne":
            query = query.where(col != val)
        elif op == "in":
            query = query.where(col.in_(val))
        elif op == "like":
            query = query.where(col.like(val))
    return query


def _eval_threshold(value: float, thresholds: list[dict]) -> str | None:
    """Tìm severity theo danh sách band threshold. First-match wins.

    Band format: {"lt": X, "severity": "critical"} hoặc {"gte": X, "severity": "warning"}.
    """
    for band in thresholds:
        sev = band.get("severity")
        matched = False
        for op in _ALLOWED_THRESHOLD_OPS:
            if op not in band:
                continue
            limit = band[op]
            if op == "lt" and value < limit:
                matched = True
            elif op == "lte" and value <= limit:
                matched = True
            elif op == "gt" and value > limit:
                matched = True
            elif op == "gte" and value >= limit:
                matched = True
            elif op == "eq" and value == limit:
                matched = True
        if matched:
            return sev if sev else None
    return None


def _render_title(template: str, **kwargs) -> str:
    """Render title_template với format_map an toàn (chỉ biến đã định sẵn)."""
    try:
        return template.format_map(kwargs)
    except (KeyError, ValueError):
        return template


def _make_finding(
    code: str,
    company_id: int,
    year: int,
    subject_key: str,
    severity: str,
    title: str,
    details: dict,
    evidence_refs: list | None = None,
) -> Finding:
    return Finding(
        company_id=company_id,
        period_year=year,
        check_code=code,
        severity=severity,
        subject_type="material_code",
        subject_key=subject_key,
        title=title,
        details=details,
        evidence_refs=evidence_refs or [],
    )


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_threshold_compare(spec: dict):
    for field in ("table", "subject_col", "metric_col", "thresholds"):
        if field not in spec:
            raise SpecValidationError(f"threshold_compare thiếu field '{field}'")
    table = spec["table"]
    if table not in _ALLOWED_TABLES:
        raise SpecValidationError(f"table '{table}' không hợp lệ")
    _get_col(_get_model(table), spec["subject_col"], table)
    _get_col(_get_model(table), spec["metric_col"], table, col_type="numeric")


def _validate_presence_check(spec: dict):
    for field in ("table_a", "join_col_a", "table_b", "join_col_b", "mode", "severity"):
        if field not in spec:
            raise SpecValidationError(f"presence_check thiếu field '{field}'")
    if spec["table_a"] not in _ALLOWED_TABLES:
        raise SpecValidationError(f"table_a '{spec['table_a']}' không hợp lệ")
    if spec["table_b"] not in _ALLOWED_TABLES:
        raise SpecValidationError(f"table_b '{spec['table_b']}' không hợp lệ")
    if spec["mode"] not in ("a_not_in_b", "b_not_in_a"):
        raise SpecValidationError(f"mode '{spec['mode']}' không hợp lệ")
    model_a = _get_model(spec["table_a"])
    model_b = _get_model(spec["table_b"])
    _get_col(model_a, spec["join_col_a"], spec["table_a"])
    _get_col(model_b, spec["join_col_b"], spec["table_b"])


def _validate_aggregate_threshold(spec: dict):
    for field in ("table", "subject_col", "agg_fn", "metric_col", "thresholds"):
        if field not in spec:
            raise SpecValidationError(f"aggregate_threshold thiếu field '{field}'")
    if spec["table"] not in _ALLOWED_TABLES:
        raise SpecValidationError(f"table '{spec['table']}' không hợp lệ")
    if spec["agg_fn"] not in _ALLOWED_AGG_FNS:
        raise SpecValidationError(f"agg_fn '{spec['agg_fn']}' không hợp lệ. Cho phép: {_ALLOWED_AGG_FNS}")
    model = _get_model(spec["table"])
    _get_col(model, spec["subject_col"], spec["table"])
    _get_col(model, spec["metric_col"], spec["table"], col_type="numeric")


def _validate_cross_table_match(spec: dict):
    for field in ("table_a", "join_col_a", "agg_fn_a", "metric_col_a",
                  "table_b", "join_col_b", "agg_fn_b", "metric_col_b", "diff_thresholds"):
        if field not in spec:
            raise SpecValidationError(f"cross_table_match thiếu field '{field}'")
    for table_key, agg_key in [("table_a", "agg_fn_a"), ("table_b", "agg_fn_b")]:
        if spec[table_key] not in _ALLOWED_TABLES:
            raise SpecValidationError(f"{table_key} '{spec[table_key]}' không hợp lệ")
        if spec[agg_key] not in _ALLOWED_AGG_FNS:
            raise SpecValidationError(f"agg_fn '{spec[agg_key]}' không hợp lệ")


def _validate_ratio_threshold(spec: dict):
    for field in ("table", "subject_col", "numerator_col", "denominator_col", "thresholds"):
        if field not in spec:
            raise SpecValidationError(f"ratio_threshold thiếu field '{field}'")
    if spec["table"] not in _ALLOWED_TABLES:
        raise SpecValidationError(f"table '{spec['table']}' không hợp lệ")
    model = _get_model(spec["table"])
    _get_col(model, spec["subject_col"], spec["table"])
    _get_col(model, spec["numerator_col"], spec["table"], col_type="numeric")
    _get_col(model, spec["denominator_col"], spec["table"], col_type="numeric")


_VALIDATORS = {
    "threshold_compare": _validate_threshold_compare,
    "presence_check": _validate_presence_check,
    "aggregate_threshold": _validate_aggregate_threshold,
    "cross_table_match": _validate_cross_table_match,
    "ratio_threshold": _validate_ratio_threshold,
}


# ---------------------------------------------------------------------------
# Kind runners
# ---------------------------------------------------------------------------

def _run_threshold_compare(
    code: str, spec: dict, session: Session, company_id: int, year: int,
) -> list[Finding]:
    model = _get_model(spec["table"])
    table = spec["table"]
    subject_col = _get_col(model, spec["subject_col"], table)
    metric_col = _get_col(model, spec["metric_col"], table, col_type="numeric")
    thresholds = spec["thresholds"]
    title_tpl = spec.get("title_template", "Phát hiện {subject_key}: {value}")

    q = select(subject_col, metric_col).where(
        model.company_id == company_id,
        model.period_year == year,
    )
    q = _apply_filters(q, model, table, spec.get("filter", {}))

    findings = []
    for subject_key, value in session.execute(q):
        if value is None:
            continue
        sev = _eval_threshold(float(value), thresholds)
        if sev is None:
            continue
        title = _render_title(title_tpl, subject_key=subject_key, value=float(value))
        findings.append(_make_finding(
            code, company_id, year, str(subject_key), sev, title,
            {"value": float(value)},
        ))
    return findings


def _run_presence_check(
    code: str, spec: dict, session: Session, company_id: int, year: int,
) -> list[Finding]:
    model_a = _get_model(spec["table_a"])
    model_b = _get_model(spec["table_b"])
    col_a = _get_col(model_a, spec["join_col_a"], spec["table_a"])
    col_b = _get_col(model_b, spec["join_col_b"], spec["table_b"])
    sev = spec["severity"]
    title_tpl = spec.get("title_template", "Thiếu tương ứng cho {subject_key}")
    mode = spec["mode"]

    q_a = select(col_a.label("key")).where(
        model_a.company_id == company_id,
        model_a.period_year == year,
    )
    q_a = _apply_filters(q_a, model_a, spec["table_a"], spec.get("filter_a", {}))

    q_b = select(col_b.label("key")).where(
        model_b.company_id == company_id,
        model_b.period_year == year,
    )
    q_b = _apply_filters(q_b, model_b, spec["table_b"], spec.get("filter_b", {}))

    set_a = {r.key for r in session.execute(q_a)}
    set_b = {r.key for r in session.execute(q_b)}

    if mode == "a_not_in_b":
        missing = set_a - set_b
    else:
        missing = set_b - set_a

    findings = []
    for key in sorted(missing):
        if key is None:
            continue
        title = _render_title(title_tpl, subject_key=str(key))
        findings.append(_make_finding(
            code, company_id, year, str(key), sev, title, {},
        ))
    return findings


def _agg_func(agg_fn: str, col):
    mapping = {
        "sum": func.sum(col),
        "count": func.count(col),
        "avg": func.avg(col),
        "max": func.max(col),
        "min": func.min(col),
    }
    return mapping[agg_fn]


def _run_aggregate_threshold(
    code: str, spec: dict, session: Session, company_id: int, year: int,
) -> list[Finding]:
    model = _get_model(spec["table"])
    table = spec["table"]
    subject_col = _get_col(model, spec["subject_col"], table)
    metric_col = _get_col(model, spec["metric_col"], table, col_type="numeric")
    agg_fn = spec["agg_fn"]
    thresholds = spec["thresholds"]
    title_tpl = spec.get("title_template", "Tổng {subject_key}: {value}")

    q = select(subject_col.label("key"), _agg_func(agg_fn, metric_col).label("val")).where(
        model.company_id == company_id,
        model.period_year == year,
    )
    q = _apply_filters(q, model, table, spec.get("filter", {}))
    q = q.group_by(subject_col)

    findings = []
    for key, val in session.execute(q):
        if val is None:
            continue
        sev = _eval_threshold(float(val), thresholds)
        if sev is None:
            continue
        title = _render_title(title_tpl, subject_key=str(key), value=float(val))
        findings.append(_make_finding(
            code, company_id, year, str(key), sev, title,
            {"value": float(val)},
        ))
    return findings


def _run_cross_table_match(
    code: str, spec: dict, session: Session, company_id: int, year: int,
) -> list[Finding]:
    model_a = _get_model(spec["table_a"])
    model_b = _get_model(spec["table_b"])
    col_a = _get_col(model_a, spec["join_col_a"], spec["table_a"])
    col_b = _get_col(model_b, spec["join_col_b"], spec["table_b"])
    metric_a = _get_col(model_a, spec["metric_col_a"], spec["table_a"], col_type="numeric")
    metric_b = _get_col(model_b, spec["metric_col_b"], spec["table_b"], col_type="numeric")

    q_a = select(col_a.label("key"), _agg_func(spec["agg_fn_a"], metric_a).label("val")).where(
        model_a.company_id == company_id,
        model_a.period_year == year,
    )
    q_a = _apply_filters(q_a, model_a, spec["table_a"], spec.get("filter_a", {}))
    q_a = q_a.group_by(col_a)

    q_b = select(col_b.label("key"), _agg_func(spec["agg_fn_b"], metric_b).label("val")).where(
        model_b.company_id == company_id,
        model_b.period_year == year,
    )
    q_b = _apply_filters(q_b, model_b, spec["table_b"], spec.get("filter_b", {}))
    q_b = q_b.group_by(col_b)

    map_a = {r.key: float(r.val or 0) for r in session.execute(q_a)}
    map_b = {r.key: float(r.val or 0) for r in session.execute(q_b)}

    all_keys = set(map_a) | set(map_b)
    thresholds = spec["diff_thresholds"]
    title_tpl = spec.get("title_template", "Lệch {subject_key}: A={val_a:.2f} B={val_b:.2f} ({pct:.1f}%)")

    findings = []
    for key in sorted(all_keys):
        if key is None:
            continue
        val_a = map_a.get(key, 0.0)
        val_b = map_b.get(key, 0.0)
        denom = max(abs(val_a), abs(val_b))
        if denom == 0:
            continue
        pct = abs(val_a - val_b) / denom * 100.0
        sev = _eval_threshold(pct, thresholds)
        if sev is None:
            continue
        title = _render_title(
            title_tpl, subject_key=str(key), val_a=val_a, val_b=val_b, pct=pct,
        )
        findings.append(_make_finding(
            code, company_id, year, str(key), sev, title,
            {"val_a": val_a, "val_b": val_b, "pct": pct},
        ))
    return findings


def _run_ratio_threshold(
    code: str, spec: dict, session: Session, company_id: int, year: int,
) -> list[Finding]:
    model = _get_model(spec["table"])
    table = spec["table"]
    subject_col = _get_col(model, spec["subject_col"], table)
    num_col = _get_col(model, spec["numerator_col"], table, col_type="numeric")
    den_col = _get_col(model, spec["denominator_col"], table, col_type="numeric")
    scale_pct = spec.get("scale_pct", False)
    thresholds = spec["thresholds"]
    title_tpl = spec.get("title_template", "Tỷ lệ {subject_key}: {value:.2f}")

    q = select(subject_col.label("key"), num_col.label("num"), den_col.label("den")).where(
        model.company_id == company_id,
        model.period_year == year,
    )
    q = _apply_filters(q, model, table, spec.get("filter", {}))

    findings = []
    for key, num, den in session.execute(q):
        if den is None or float(den) == 0:
            continue
        ratio = float(num or 0) / float(den)
        value = ratio * 100.0 if scale_pct else ratio
        sev = _eval_threshold(value, thresholds)
        if sev is None:
            continue
        title = _render_title(title_tpl, subject_key=str(key), value=value)
        findings.append(_make_finding(
            code, company_id, year, str(key), sev, title,
            {"value": value},
        ))
    return findings


_KIND_RUNNERS = {
    "threshold_compare": _run_threshold_compare,
    "presence_check": _run_presence_check,
    "aggregate_threshold": _run_aggregate_threshold,
    "cross_table_match": _run_cross_table_match,
    "ratio_threshold": _run_ratio_threshold,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DynamicCheckRunner:
    """Runner cho 1 check định nghĩa bằng DSL.

    Validate spec khi khởi tạo (fail fast). Run tách biệt để xử lý nhiều DN.
    """

    def __init__(self, code: str, spec: dict):
        self.code = code
        self.spec = spec
        kind = spec.get("kind")
        if kind not in _VALIDATORS:
            raise SpecValidationError(
                f"kind '{kind}' không hợp lệ. Hỗ trợ: {sorted(_VALIDATORS)}"
            )
        _VALIDATORS[kind](spec)

    def run(self, session: Session, company_id: int, year: int) -> list[Finding]:
        kind = self.spec["kind"]
        runner_fn = _KIND_RUNNERS[kind]
        return runner_fn(self.code, self.spec, session, company_id, year)
