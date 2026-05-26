"""AI-assisted spec generation cho dynamic check catalog.

Gọi model deep (Gemini 2.5 Pro) với few-shot 5 ví dụ phủ cả 5 kind DSL.
KHÔNG dùng fallback provider — nếu AI fail trả SpecGenError rõ ràng để
admin biết và nhập spec tay thay vì silent downgrade.

Caller phải catch SpecGenError và hiển thị message cho user.
"""

from __future__ import annotations

import json
import logging
import re

from app.ai.client import make_client
from app.ai.config import get_setting
from app.checks.dynamic_runner import (
    _VALIDATORS,
    SpecValidationError,
)

log = logging.getLogger(__name__)


class SpecGenError(Exception):
    """Lỗi khi AI không thể sinh spec hợp lệ. Message dành cho hiển thị UI."""


# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_SCHEMA_HINT = """
Các bảng và cột được phép dùng trong spec:

nvl_balances (M15 cân đối NVL):
  subject cols: material_code, material_name, unit
  metric cols:  opening_qty, import_qty, reexport_qty, repurpose_qty,
                production_out_qty, other_out_qty, closing_qty

sp_balances (M15a cân đối TP):
  subject cols: product_code, product_name, unit
  metric cols:  opening_qty, intake_qty, repurpose_qty, export_qty,
                other_out_qty, closing_qty

declaration_lines (BCCT tờ khai XNK):
  subject cols: declaration_no, customs_code, item_code, hs_code,
                unit, currency, origin, partner
  metric cols:  quantity, unit_price, value_foreign, value_total, tax_total

norms (M16 định mức):
  subject cols: product_code, material_code, product_unit, material_unit
  metric cols:  norm_qty
""".strip()

_THRESHOLD_HINT = """
Format threshold (lt-ascending bands, first-match wins):
  {"lt": 5, "severity": null}     ← dưới 5 → không fire
  {"lt": 20, "severity": "info"}  ← 5-20 → Thông tin
  {"gte": 20, "severity": "warning"} ← ≥20 → Cảnh báo

Giá trị severity hợp lệ: "critical", "warning", "info", null (không fire).
""".strip()

_FEW_SHOTS = [
    {
        "description": "Tìm các mã NVL có tồn kho cuối kỳ âm",
        "spec": {
            "kind": "threshold_compare",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "metric_col": "closing_qty",
            "thresholds": [{"lt": 0, "severity": "critical"}],
            "title_template": "Tồn cuối {subject_key} âm ({value:.2f})",
        },
    },
    {
        "description": "Phát hiện mã NVL có nhập khẩu nhưng không xuất hiện trong tờ khai BCCT",
        "spec": {
            "kind": "presence_check",
            "table_a": "nvl_balances",
            "join_col_a": "material_code",
            "filter_a": {"import_qty__gt": 0},
            "table_b": "declaration_lines",
            "join_col_b": "item_code",
            "filter_b": {},
            "mode": "a_not_in_b",
            "severity": "critical",
            "title_template": "Mã NVL {subject_key} có nhập nhưng thiếu tờ khai",
        },
    },
    {
        "description": "Kiểm tra tổng số lượng nhập NVL theo mã vượt ngưỡng 50000 đơn vị",
        "spec": {
            "kind": "aggregate_threshold",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "agg_fn": "sum",
            "metric_col": "import_qty",
            "thresholds": [
                {"lt": 50000, "severity": None},
                {"gte": 50000, "severity": "info"},
            ],
            "title_template": "Tổng nhập {subject_key}: {value:.2f} vượt ngưỡng",
        },
    },
    {
        "description": "So sánh số lượng xuất TP trong M15a với tờ khai xuất E15",
        "spec": {
            "kind": "cross_table_match",
            "table_a": "sp_balances",
            "join_col_a": "product_code",
            "agg_fn_a": "sum",
            "metric_col_a": "export_qty",
            "filter_a": {},
            "table_b": "declaration_lines",
            "join_col_b": "item_code",
            "agg_fn_b": "sum",
            "metric_col_b": "quantity",
            "filter_b": {"customs_code__in": ["E15"]},
            "diff_thresholds": [
                {"lt": 1, "severity": None},
                {"lt": 5, "severity": "info"},
                {"lt": 20, "severity": "warning"},
                {"gte": 20, "severity": "critical"},
            ],
            "title_template": "Lệch xuất {subject_key}: M15a={val_a:.2f} BCCT={val_b:.2f} ({pct:.1f}%)",
        },
    },
    {
        "description": "Cảnh báo nếu tỷ lệ chuyển mục đích sử dụng NVL vượt 25%",
        "spec": {
            "kind": "ratio_threshold",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "numerator_col": "repurpose_qty",
            "denominator_col": "import_qty",
            "scale_pct": True,
            "thresholds": [
                {"lt": 10, "severity": None},
                {"lt": 25, "severity": "warning"},
                {"gte": 25, "severity": "critical"},
            ],
            "title_template": "Tỷ lệ chuyển MĐSD {subject_key}: {value:.1f}%",
        },
    },
]


def _build_system_prompt() -> str:
    examples_block = "\n\n".join(
        f"Ví dụ {i + 1}:\n"
        f"Mô tả: {ex['description']}\n"
        f"Spec: {json.dumps(ex['spec'], ensure_ascii=False)}"
        for i, ex in enumerate(_FEW_SHOTS)
    )
    kinds = ", ".join(sorted(_VALIDATORS.keys()))
    return f"""Bạn là chuyên gia viết spec kiểm tra cho hệ thống kiểm toán hải quan Việt Nam (Audit-HQ).

{_SCHEMA_HINT}

Các loại kiểm tra (kind) hợp lệ: {kinds}

{_THRESHOLD_HINT}

{examples_block}

Nhiệm vụ: Từ mô tả nghiệp vụ của admin, sinh ra 1 spec JSON hoàn chỉnh, hợp lệ.
Chỉ trả về JSON object thuần túy. KHÔNG giải thích. KHÔNG dùng markdown code fence.
Tất cả tên field phải đúng chính xác theo schema trên."""


def _call_ai(messages: list[dict], model: str, max_tokens: int = 1024):
    """Gọi AI, không dùng fallback. Raise gốc khi lỗi."""
    client = make_client()
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        max_tokens=max_tokens,
    )


def _extract_json(text: str) -> dict:
    """Parse JSON từ response AI, xử lý markdown fence nếu có."""
    text = text.strip()
    # Strip ```json...``` hoặc ```...```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SpecGenError(f"AI trả về nội dung không phải JSON hợp lệ: {e}") from e


def generate_spec(description: str, kind_hint: str | None = None) -> dict:
    """Gọi AI để sinh spec DSL từ mô tả nghiệp vụ tiếng Việt.

    Validate spec qua DynamicCheckRunner trước khi trả về.
    Raise SpecGenError nếu AI fail hoặc spec không hợp lệ.
    """
    if not description or not description.strip():
        raise SpecGenError("Mô tả không được trống.")

    model = get_setting("model_deep")
    if not model:
        raise SpecGenError("Chưa cấu hình model_deep trong AI Settings.")

    user_content = f"Mô tả: {description.strip()}"
    if kind_hint and kind_hint in _VALIDATORS:
        user_content += f"\nLoại kiểm tra mong muốn: {kind_hint}"

    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": user_content},
    ]

    try:
        resp = _call_ai(messages=messages, model=model)
    except Exception as exc:
        log.warning("spec_gen AI call failed: %s", exc)
        raise SpecGenError(f"Gọi AI thất bại: {exc}") from exc

    raw = resp.choices[0].message.content or ""
    spec = _extract_json(raw)

    # Validate spec qua DynamicCheckRunner (dry-run với code dummy).
    try:
        from app.checks.dynamic_runner import DynamicCheckRunner
        DynamicCheckRunner(code="X.0", spec=spec)
    except SpecValidationError as e:
        raise SpecGenError(f"Spec AI sinh ra không hợp lệ: {e}") from e

    return spec
