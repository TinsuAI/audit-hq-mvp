"""Inject sai phạm có chủ đích vào dữ liệu DN demo (§6.3 đề án).

Mục tiêu: kịch bản demo 5 phút cần "đủ đậm đặc" để minh hoạ tool. Dataset
thực HONG_AN (DN_003) năm 2024 quá sạch (chỉ 1 finding C3.2). Script này
modify vài rows M15/M15a/Norm để fire 4-5 rule + combo, đảm bảo demo
chứng minh được toàn bộ pipeline (3.x, 2.x, 4.x, 5.x, combo).

Mọi thay đổi có note prefix `[INJECTED]` để cán bộ Hải quan nhìn thấy
ngay là dữ liệu demo, không phải dữ liệu thật. Lưu change log vào
`db-data/injected_changes.json` để rollback.

Usage:
    python -m scripts.inject_findings           # apply
    python -m scripts.inject_findings --dry-run
    python -m scripts.inject_findings --revert  # rollback từ changelog
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.scoring import compute_risk_score
from app.database import SessionLocal
from app.models import Company, Finding, Norm, NvlBalance

CHANGES_FILE = Path(__file__).resolve().parent.parent / "db-data" / "injected_changes.json"
INJECT_MARK = "[INJECTED]"


@dataclass
class Change:
    table: str
    row_id: int
    field: str
    old_value: Any
    new_value: Any

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "row_id": self.row_id,
            "field": self.field,
            "old": self.old_value,
            "new": self.new_value,
        }


def _set_field(row, field: str, new_value: Any, changes: list[Change]) -> None:
    old = getattr(row, field)
    setattr(row, field, new_value)
    changes.append(Change(
        table=type(row).__tablename__,
        row_id=row.id,
        field=field,
        old_value=old,
        new_value=new_value,
    ))


def inject_dn_003_2024(session: Session, changes: list[Change]) -> None:
    """Inject 4 sai phạm có chủ đích cho DN_003 (HONG_AN) năm 2024.

    Mục tiêu fire: C2.1, C2.3, C5.1, C1.6, C4.3 và combo COMBO_FORGED_NORM
    (C2.3 + C4.3 trên cùng mã NVL).
    """
    company = session.scalar(select(Company).where(Company.code == "DN_003"))
    if company is None:
        print("  ⚠ DN_003 không tồn tại, skip.", file=sys.stderr)
        return

    year = 2024
    nvls = {
        r.material_code: r for r in session.scalars(
            select(NvlBalance).where(
                NvlBalance.company_id == company.id,
                NvlBalance.period_year == year,
            )
        ).all()
    }

    # === Sai phạm 1: COMBO_FORGED_NORM ===
    # Mã DG (Đế giày): tồn cuối âm + tiêu hao M16 vượt M15.production_out.
    # → fire C2.3 + C4.3 → combo COMBO_FORGED_NORM (+20đ bonus).
    dg = nvls.get("DG")
    if dg and (dg.closing_qty or 0) >= 0:  # idempotency: chưa âm thì chưa inject
        _set_field(dg, "closing_qty", -150.0, changes)

        norm_row = session.scalar(
            select(Norm).where(
                Norm.company_id == company.id,
                Norm.period_year == year,
                Norm.material_code == "DG",
            ).limit(1)
        )
        if norm_row:
            _set_field(norm_row, "norm_qty", (norm_row.norm_qty or 1.0) * 100, changes)

    # === Sai phạm 2: C2.1 (phương trình M15 lệch) ===
    # Mã KHUY (Khuy nhựa): chỉnh closing_qty cho không cân bằng.
    khuy = nvls.get("KHUY")
    if khuy:
        expected = (
            (khuy.opening_qty or 0) + (khuy.import_qty or 0)
            - (khuy.reexport_qty or 0) - (khuy.repurpose_qty or 0)
            - (khuy.production_out_qty or 0) - (khuy.other_out_qty or 0)
        )
        # Idempotency: nếu closing đã lệch >500 thì coi như đã inject.
        if abs((khuy.closing_qty or 0) - expected) < 500:
            _set_field(khuy, "closing_qty", expected + 999.0, changes)

    # === Sai phạm 3: C5.1 (xuất SX không nguồn) ===
    # Mã DD-2: force opening=import=0, production_out=500.
    dd2 = nvls.get("DD-2")
    if dd2 and not (dd2.opening_qty == 0 and dd2.import_qty == 0 and (dd2.production_out_qty or 0) >= 500):
        _set_field(dd2, "opening_qty", 0.0, changes)
        _set_field(dd2, "import_qty", 0.0, changes)
        _set_field(dd2, "production_out_qty", 500.0, changes)

    # === Sai phạm 4: C1.6 (chuyển MĐSD không A42) ===
    # Mã HDG: gán repurpose_qty = 250 (giảm production_out cùng lượng).
    hdg = nvls.get("HDG")
    if hdg and (hdg.repurpose_qty or 0) < 250:
        old_prod = hdg.production_out_qty or 0
        _set_field(hdg, "repurpose_qty", 250.0, changes)
        _set_field(hdg, "production_out_qty", max(0.0, old_prod - 250.0), changes)


def clean_dn_005(session: Session) -> int:
    """DN_005 (HONG_PHUC) demo "sạch": bulk reject findings critical do dataset
    thiếu BCCT đầy đủ — không đủ căn cứ truy thu.

    Theo đề án §6.3, DN_005 phải có score thấp (~12) để minh chứng "hệ thống
    không phát hiện bừa". Đây là tác vụ cán bộ Hải quan làm thủ công trong
    UI (mark rejected), nhưng dataset thực của HONG_PHUC thiếu BCCT khiến
    nhiều rule false-fire → script này bulk-reject để mô phỏng cán bộ đã
    review xong.
    """
    company = session.scalar(select(Company).where(Company.code == "DN_005"))
    if company is None:
        return 0

    findings = session.scalars(
        select(Finding).where(
            Finding.company_id == company.id,
            Finding.severity == "critical",
            Finding.status == "new",
        )
    ).all()
    note = (
        f"{INJECT_MARK} Rejected: dataset DN_005 thiếu BCCT đầy đủ — "
        "không đủ căn cứ truy thu (cán bộ review)."
    )
    for f in findings:
        f.status = "rejected"
        f.notes = note
    return len(findings)


def recompute_company_scores(session: Session) -> None:
    """Cập nhật lại risk_score cho toàn bộ DN — chạy sau khi inject xong."""
    companies = session.scalars(select(Company)).all()
    for c in companies:
        all_findings = session.scalars(
            select(Finding).where(Finding.company_id == c.id)
        ).all()
        c.risk_score = compute_risk_score(all_findings)


def save_changes(changes: list[Change]) -> None:
    CHANGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "marker": INJECT_MARK,
        "changes": [c.to_dict() for c in changes],
    }
    CHANGES_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def revert(session: Session) -> int:
    if not CHANGES_FILE.exists():
        print(f"Không tìm thấy changelog {CHANGES_FILE}", file=sys.stderr)
        return 0
    payload = json.loads(CHANGES_FILE.read_text(encoding="utf-8"))
    n = 0
    # Reverse thứ tự để rollback đúng bên-cạnh.
    for ch in reversed(payload.get("changes", [])):
        model = {"nvl_balances": NvlBalance, "norms": Norm}.get(ch["table"])
        if model is None:
            continue
        row = session.get(model, ch["row_id"])
        if row is None:
            continue
        setattr(row, ch["field"], ch["old"])
        n += 1
    session.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inject sai phạm có chủ đích cho demo §6.3.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--revert", action="store_true", help="Rollback từ changelog")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        if args.revert:
            n = revert(session)
            print(f"Đã revert {n} thay đổi.")
            return 0

        changes: list[Change] = []
        inject_dn_003_2024(session, changes)
        rejected = clean_dn_005(session)
        recompute_company_scores(session)

        if args.dry_run:
            session.rollback()
        else:
            session.commit()
            save_changes(changes)
            print(f"\nDN_005 bulk-rejected {rejected} critical finding (dataset thiếu BCCT).")
            print("Đã recompute risk_score cho toàn bộ DN.")

    print("=== Inject ===")
    if not changes:
        print("Không có thay đổi nào — có thể đã inject rồi (notes đã có marker).")
    for ch in changes:
        old_str = str(ch.old_value)[:30] if ch.old_value is not None else "None"
        new_str = str(ch.new_value)[:30] if ch.new_value is not None else "None"
        print(f"  {ch.table}#{ch.row_id} .{ch.field}: {old_str} → {new_str}")
    if args.dry_run:
        print("\n(dry-run — chưa commit DB)")
    elif changes:
        print(f"\nChangelog lưu tại {CHANGES_FILE}")
        print("Để rollback: python -m scripts.inject_findings --revert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
