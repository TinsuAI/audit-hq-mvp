"""Combination signatures — phát hiện kết hợp (§2.7 đề án).

Một số kết hợp findings có ý nghĩa nghiệp vụ vượt trội tổng các phần. Mỗi
combo tạo ra một "meta-finding" với `check_code` prefix `COMBO_` và
`evidence_refs` trỏ về các finding gốc.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.checks.registry import Severity
from app.models import Finding


@dataclass(frozen=True)
class CombinationSpec:
    code: str                # vd "COMBO_FORGED_NORM"
    title: str               # Tiêu đề ngắn
    description: str         # Nghiệp vụ giải thích
    triggers: tuple[str, ...]  # Mã check phải đồng thời fire trên cùng subject
    severity: Severity = Severity.CRITICAL


COMBOS: list[CombinationSpec] = [
    CombinationSpec(
        code="COMBO_FORGED_NORM",
        title="Tồn âm + tiêu hao M16 vượt M15 — nghi tạo định mức ảo",
        description=(
            "Cùng một mã NVL vừa có tồn cuối âm (C2.3) vừa có tiêu hao M16 vượt "
            "xuất SX M15 (C4.3). Pattern điển hình của \"tạo định mức ảo\" để hợp "
            "thức hoá NVL nhập miễn thuế nhưng đã bán nội địa."
        ),
        triggers=("C2.3", "C4.3"),
    ),
    CombinationSpec(
        code="COMBO_UNDECLARED_SOURCE",
        title="Nhập M15 không tờ khai + xuất SX không nguồn — nghi NVL nội địa lậu",
        description=(
            "Cùng một mã NVL có nhập trong M15 không có tờ khai (C1.3) và có "
            "xuất sản xuất không có nguồn nhập/tồn (C5.1). Khả năng DN dùng NVL "
            "nội địa không khai báo, đưa vào phạm vi miễn thuế."
        ),
        triggers=("C1.3", "C5.1"),
    ),
    CombinationSpec(
        code="COMBO_ACCOUNTING_INCONSISTENT",
        title="Phương trình M15 lệch + tiêu hao M16 bất thường — số liệu mâu thuẫn",
        description=(
            "Cùng một mã NVL có phương trình M15 không cân (C2.1) và tiêu hao "
            "M16 vượt M15 (C4.3). Số liệu giữa các nguồn báo cáo không khớp; "
            "cần làm rõ cột nào sai trước khi xét các phát hiện khác."
        ),
        triggers=("C2.1", "C4.3"),
    ),
    CombinationSpec(
        code="COMBO_HS_GAMING",
        title="HS bất nhất + đơn vị tính lệch — nghi cố tình phân loại sai",
        description=(
            "Cùng một mã vật tư có cả mã HS không nhất quán (C3.2) và đơn vị "
            "tính lệch giữa M15 và BCCT (C3.3). Có thể là cố tình đổi mã HS để "
            "né chính sách hoặc nguỵ tạo cùng lúc nhiều thuộc tính cơ bản."
        ),
        triggers=("C3.2", "C3.3"),
        severity=Severity.WARNING,
    ),
]


def detect_combos(
    session: Session,
    company_id: int,
    year: int,
    existing_findings: Sequence[Finding],
) -> list[Finding]:
    """Quét findings vừa run, tìm combo theo subject_key.

    Mỗi combo fire khi tất cả `triggers` đều có finding với cùng `subject_key`
    trên cùng (company, year). Trả về list Finding mới (chưa add vào session).
    """
    # Index findings by check_code → {subject_key: [Finding...]}
    by_check: dict[str, dict[str, list[Finding]]] = defaultdict(lambda: defaultdict(list))
    for f in existing_findings:
        if f.check_code.startswith("COMBO_") or not f.subject_key:
            continue
        by_check[f.check_code][f.subject_key].append(f)

    meta_findings: list[Finding] = []
    for combo in COMBOS:
        # Cần có ít nhất 1 finding ở mỗi check trong combo.
        if not all(code in by_check for code in combo.triggers):
            continue
        # Tìm subject_key xuất hiện ở tất cả check trong combo.
        subjects = set(by_check[combo.triggers[0]].keys())
        for code in combo.triggers[1:]:
            subjects &= set(by_check[code].keys())
        for subj in sorted(subjects):
            triggered_findings: list[Finding] = []
            for code in combo.triggers:
                triggered_findings.extend(by_check[code][subj])
            meta_findings.append(Finding(
                company_id=company_id,
                period_year=year,
                check_code=combo.code,
                severity=combo.severity.value,
                subject_type=triggered_findings[0].subject_type,
                subject_key=subj,
                title=f"[{subj}] {combo.title}",
                details={
                    "triggers": list(combo.triggers),
                    "description": combo.description,
                    "trigger_finding_ids": [
                        f.id for f in triggered_findings if f.id is not None
                    ],
                },
                evidence_refs=[
                    {"table": "findings", "filter": {"id": f.id}}
                    for f in triggered_findings
                    if f.id is not None
                ],
            ))
    return meta_findings


# Public catalog cho UI / registry hiển thị.
COMBO_SPECS: dict[str, CombinationSpec] = {c.code: c for c in COMBOS}
