"""AI chẩn đoán cấu trúc file BCQT/BCCT khi nạp lỗi — escalation tùy chọn của
`app/pipeline/validate.py`.

Heuristic (validate) đã chỉ ra lệch cột theo luật. Khi cán bộ muốn giải thích sâu
hơn / map mẫu lạ, module này gửi trích đoạn sheet thật + schema mong đợi cho LLM
(slot "fast", fallback chain sẵn có) để diễn giải tiếng Việt + gợi ý sửa.

Không gọi trong rule logic; chỉ chạy theo yêu cầu lúc onboarding dữ liệu.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from app.ai.client import (
    call_with_fallback,
    fallback_model_for,
    make_client,
    make_fallback_client,
)
from app.ai.config import get_setting
from app.pipeline.discover import discover
from app.pipeline.validate import SLOT_LABEL, diagnose_upload

_EXPECTED = {
    "m15": "Mẫu 15 (NVL) TT39: sheet 'BCQT_NPL'; dữ liệu từ hàng 9 (0-index). "
           "Cột: 0=STT, 1=Mã NVL, 2=Tên, 3=ĐVT, 4=Tồn đầu, 5=Nhập, 6=Tái xuất, "
           "7=Chuyển MĐSD, 8=Xuất sản xuất, 9=Xuất khác, 10=Tồn cuối.",
    "m15a": "Mẫu 15a (TP) TT39: sheet 'BCQT_SP'; dữ liệu từ hàng 9. "
            "Cột: 0=STT, 1=Mã SP, 2=Tên, 3=ĐVT, 4=Tồn đầu, 5=Nhập, 6=Chuyển MĐSD, "
            "7=Xuất khẩu, 8=Xuất khác, 9=Tồn cuối.",
    "m16": "Mẫu 16 (Định mức) TT39: sheet 'BCTT39'; dữ liệu từ hàng 11; cấu trúc "
           "SP→NVL (forward-fill SP). Cột: 1=Mã SP, 2=Tên SP, 3=ĐVT SP, 4=Mã NVL, "
           "5=Tên NVL, 6=ĐVT NVL, 7=Định mức, 8=Ghi chú.",
    "bcct": "BCCT (tờ khai): sheet 'Sheet1'; dữ liệu từ hàng 10; số tờ khai 9-13 "
            "chữ số ở cột 1, ngày cột 2, loại hình cột 3, mã hàng cột 20.",
}


def _excerpt(path: Path, n_rows: int = 12, n_cols: int = 14) -> str:
    """Trích sheet đầu thành lưới text gọn (hàng × cột) cho LLM đọc."""
    try:
        xls = pd.ExcelFile(path)
        df = pd.read_excel(xls, sheet_name=0, header=None, nrows=n_rows)
    except Exception as e:  # noqa: BLE001
        return f"(không đọc được: {type(e).__name__})"
    lines = [f"Sheets: {xls.sheet_names}"]
    for ri, row in enumerate(df.values.tolist()):
        cells = []
        for c in row[:n_cols]:
            if c is None or (isinstance(c, float) and math.isnan(c)):
                s = ""
            else:
                s = str(c)
            cells.append(s[:20])
        lines.append(f"H{ri}: " + " | ".join(cells))
    return "\n".join(lines)


def diagnose_with_ai(code: str, year: int, raw_root: Path) -> str:
    """Gọi LLM chẩn đoán các slot lỗi. Trả văn bản tiếng Việt (rỗng nếu không có lỗi)."""
    diag = diagnose_upload(code, year, Path(raw_root))
    if not diag.has_errors:
        return "Không còn lỗi nặng để chẩn đoán."

    files = discover(code, year, Path(raw_root))
    slot_path = {
        "m15": files.m15, "m15a": files.m15a, "m16": files.m16,
        "bcct": files.bcct[0] if files.bcct else None,
    }
    error_slots = {d.slot for d in diag.errors}

    blocks = []
    for slot in ("m15", "m15a", "m16", "bcct"):
        if slot not in error_slots or not slot_path.get(slot):
            continue
        blocks.append(
            f"### {SLOT_LABEL[slot]}\n"
            f"MONG ĐỢI: {_EXPECTED[slot]}\n"
            f"FILE THỰC TẾ (12 hàng đầu, 14 cột đầu):\n{_excerpt(slot_path[slot])}"
        )
    if not blocks:
        return "Không có file tương ứng với slot lỗi để chẩn đoán."

    system = (
        "Bạn là trợ lý kỹ thuật giúp cán bộ Hải quan nạp dữ liệu BCQT/BCCT vào hệ "
        "thống Audit-HQ. Hệ thống đọc file theo VỊ TRÍ CỘT cố định (mẫu TT39/ECUS). "
        "Với mỗi file lỗi, hãy: (1) xác định đây là loại gì; (2) chỉ ra dòng tiêu đề "
        "và vị trí cột THỰC TẾ so với mong đợi; (3) nêu rõ lệch ở đâu; (4) hướng dẫn "
        "ngắn gọn cách sửa (đổi mẫu, dời cột, hay chọn sheet đúng). Trả lời tiếng "
        "Việt, ngắn gọn, có gạch đầu dòng. Không bịa số liệu."
    )
    user = "Chẩn đoán các file sau:\n\n" + "\n\n".join(blocks)

    resp = call_with_fallback(
        primary_client=make_client(),
        primary_model=get_setting("model_fast"),
        fallback_client=make_fallback_client(),
        fallback_model=fallback_model_for("fast"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=800,
    )
    return (resp.choices[0].message.content or "").strip() or "(AI không trả lời nội dung)"
