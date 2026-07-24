"""Kho map cột đã xác nhận + resolve `officer-confirmed` (WS1-3, ADR #18).

Chứng minh: round-trip lưu/nạp; map lưu khớp → cột resolve `officer-confirmed` →
`verified`; CÙNG DN tái dùng chéo năm (vân tay không chứa năm); DN KHÁC cùng shape
KHÔNG kế thừa xác nhận.
"""

from __future__ import annotations

from app.adapters._common import ParseProvenance
from app.adapters.evidence import (
    OFFICER_CONFIRMED,
    POSITION_ONLY,
    VERIFIED,
)
from app.checks.registry import review_state
from app.models import Company, DataFile, DataFileStatus, SavedColumnMap
from app.pipeline.data_files import (
    record_parse_result,
    sync_data_files,
    year_review_gate,
)
from app.pipeline.ingest import IngestStats
from app.pipeline.saved_map import (
    load_column_map,
    resolve_officer_confirmed,
    save_column_map,
)

_SIG = "a1b2c3d4" * 4  # vân tay giả, ổn định

_M15_COLMAP = {
    "material_code": 1, "opening_qty": 4, "import_qty": 5, "reexport_qty": 6,
    "repurpose_qty": 7, "production_out_qty": 8, "other_out_qty": 9, "closing_qty": 10,
}
_M15_EVIDENCE = {f: POSITION_ONLY for f in _M15_COLMAP}


def test_save_load_round_trip(session, company):
    save_column_map(
        session, company.id, "m15", _SIG, _M15_COLMAP, _M15_EVIDENCE, confirmed_by=None,
    )
    session.commit()
    row = load_column_map(session, company.id, "m15", _SIG)
    assert row is not None
    assert row.column_map_obj == _M15_COLMAP
    assert row.evidence_obj == _M15_EVIDENCE
    assert row.slot == "m15"


def test_save_is_idempotent_upsert(session, company):
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP)
    save_column_map(session, company.id, "m15", _SIG, {"material_code": 2})
    session.commit()
    rows = session.query(SavedColumnMap).filter_by(company_id=company.id, slot="m15").all()
    assert len(rows) == 1  # cùng khoá → ghi đè, không tạo dòng mới
    assert rows[0].column_map_obj == {"material_code": 2}


def test_resolution_marks_columns_officer_confirmed(session, company):
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP, _M15_EVIDENCE)
    session.commit()
    resolved = resolve_officer_confirmed(session, company.id, "m15", _SIG, dict(_M15_EVIDENCE))
    # Cột dùng riêng lẻ position-only vốn needs_review → sau resolve verified.
    assert resolved["production_out_qty"] == OFFICER_CONFIRMED
    assert review_state("m15", "production_out_qty", resolved["production_out_qty"]) == VERIFIED
    assert all(v == OFFICER_CONFIRMED for v in resolved.values())


def test_no_saved_map_leaves_evidence_unchanged(session, company):
    resolved = resolve_officer_confirmed(session, company.id, "m15", _SIG, dict(_M15_EVIDENCE))
    assert resolved == _M15_EVIDENCE


def test_none_signature_leaves_evidence_unchanged(session, company):
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP)
    session.commit()
    resolved = resolve_officer_confirmed(session, company.id, "m15", None, dict(_M15_EVIDENCE))
    assert resolved == _M15_EVIDENCE


def test_same_dn_cross_year_reuse(session, company):
    # Vân tay không chứa năm → cùng (DN, slot, vân tay) khớp cho mọi năm.
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP, _M15_EVIDENCE)
    session.commit()
    # File năm khác của CÙNG DN (cùng shape ⇒ cùng vân tay) vẫn resolve.
    resolved = resolve_officer_confirmed(session, company.id, "m15", _SIG, dict(_M15_EVIDENCE))
    assert resolved["production_out_qty"] == OFFICER_CONFIRMED


def test_different_dn_does_not_inherit(session, company):
    other = Company(code="OTHER_DN", tax_id="1234567890", name="DN khác")
    session.add(other)
    session.commit()
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP, _M15_EVIDENCE)
    session.commit()
    # DN khác cùng shape (cùng vân tay) KHÔNG kế thừa → evidence nguyên.
    resolved = resolve_officer_confirmed(session, other.id, "m15", _SIG, dict(_M15_EVIDENCE))
    assert resolved == _M15_EVIDENCE
    assert load_column_map(session, other.id, "m15", _SIG) is None


# --- Wiring: record_parse_result nâng officer-confirmed → gate auto-advance ---

def _touch(root, code, year, subdir, name):
    d = root / code / str(year) / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(b"x")


def _stats_position_only(code):
    return IngestStats(
        company_code=code, period_year=2024, m15_rows=5,
        provenance={"m15": ParseProvenance(
            layout="standard",
            detail={"form_signature": _SIG, "column_map": _M15_COLMAP},
            evidence=dict(_M15_EVIDENCE),
        )},
    )


def test_record_parse_result_auto_verifies_with_saved_map(session, company, tmp_path):
    _touch(tmp_path, company.code, 2024, "BCQT", "Mau15_NVL.xlsx")
    sync_data_files(session, company, raw_root=tmp_path)
    save_column_map(session, company.id, "m15", _SIG, _M15_COLMAP, _M15_EVIDENCE)
    session.commit()

    record_parse_result(session, company, 2024, _stats_position_only(company.code), committed=False)
    row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
    detail = row.parse_detail_obj
    # Toàn cột officer-confirmed → review verified → cổng không kích.
    assert detail["review"] == VERIFIED
    assert all(c["evidence"] == OFFICER_CONFIRMED for c in detail["columns"])
    assert year_review_gate(session, company, 2024) is None


def test_record_parse_result_needs_review_without_saved_map(session, company, tmp_path):
    # Không có map lưu: cùng bằng chứng position-only → needs_review, cổng kích.
    _touch(tmp_path, company.code, 2024, "BCQT", "Mau15_NVL.xlsx")
    sync_data_files(session, company, raw_root=tmp_path)
    record_parse_result(session, company, 2024, _stats_position_only(company.code), committed=False)
    row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
    assert row.parse_detail_obj["review"] == "needs_review"
    assert row.parse_status == DataFileStatus.ANALYZED
    assert year_review_gate(session, company, 2024) is not None
