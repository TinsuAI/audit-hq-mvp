"""Tests — vòng đời file `uploaded → analyzed → parsed` + cổng review (ADR #18).

Trục lifecycle (`parse_status`) ĐỘC LẬP trục review (`parse_detail.review`): file có
thể `parsed` mà vẫn `needs_review`. Cổng review quyết định tự advance (mọi cột
`verified`) hay dừng ở `analyzed` (có cột `needs_review`, chưa có map lưu).
"""

from __future__ import annotations

from app.adapters._common import ParseProvenance
from app.adapters.evidence import HEADER_MATCHED, POSITION_ONLY
from app.models import DataFile, DataFileStatus
from app.pipeline.data_files import (
    record_parse_result,
    review_gate_for_files,
    should_stop_for_review,
    sync_data_files,
    year_review_gate,
)
from app.pipeline.ingest import IngestStats


def _touch(root, code, year, subdir, name, content=b"x"):
    d = root / code / str(year) / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(content)
    return p


# Bằng chứng m15: mọi cột khớp tiêu đề (verified) trừ khi override.
_M15_VERIFIED = {
    "material_code": HEADER_MATCHED, "opening_qty": HEADER_MATCHED,
    "import_qty": HEADER_MATCHED, "reexport_qty": HEADER_MATCHED,
    "repurpose_qty": HEADER_MATCHED, "production_out_qty": HEADER_MATCHED,
    "other_out_qty": HEADER_MATCHED, "closing_qty": HEADER_MATCHED,
}


def _m15_stats(company_code, *, rows=5, evidence=None):
    ev = dict(_M15_VERIFIED)
    if evidence:
        ev.update(evidence)
    return IngestStats(
        company_code=company_code, period_year=2024, m15_rows=rows,
        provenance={"m15": ParseProvenance(layout="standard", evidence=ev)},
    )


def _seed_m15(session, company, tmp_path):
    _touch(tmp_path, company.code, 2024, "BCQT", "Mau15_NVL.xlsx")
    sync_data_files(session, company, raw_root=tmp_path)


class TestLifecycleStatus:
    def test_committed_false_records_analyzed(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        record_parse_result(session, company, 2024, _m15_stats(company.code), committed=False)
        row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ANALYZED
        assert row.row_count == 5

    def test_committed_true_records_parsed(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        record_parse_result(session, company, 2024, _m15_stats(company.code), committed=True)
        row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK  # "parsed"

    def test_badge_axis_independent_of_lifecycle(self, session, company, tmp_path):
        # File có thể `parsed` (OK) VÀ `needs_review` cùng lúc — hai trục riêng.
        _seed_m15(session, company, tmp_path)
        stats = _m15_stats(company.code, evidence={"production_out_qty": POSITION_ONLY})
        record_parse_result(session, company, 2024, stats, committed=True)
        row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.OK              # lifecycle: parsed
        assert row.parse_detail_obj["review"] == "needs_review"   # review: cần xác nhận


class TestReviewGate:
    def test_verified_file_no_gate_auto_advances(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        record_parse_result(session, company, 2024, _m15_stats(company.code), committed=False)
        gate = year_review_gate(session, company, 2024)
        assert gate is None
        assert should_stop_for_review(gate) is False  # tự advance, không thêm click

    def test_needs_review_stops_at_analyzed_and_names_columns(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        stats = _m15_stats(company.code, evidence={"production_out_qty": POSITION_ONLY})
        record_parse_result(session, company, 2024, stats, committed=False)
        row = session.query(DataFile).filter_by(company_id=company.id, slot="m15").first()
        assert row.parse_status == DataFileStatus.ANALYZED  # DỪNG, chưa commit

        gate = year_review_gate(session, company, 2024)
        assert gate is not None
        assert should_stop_for_review(gate) is True
        fields = {c.field for c in gate.columns}
        assert "production_out_qty" in fields

    def test_gate_lists_affected_checks(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        stats = _m15_stats(company.code, evidence={"production_out_qty": POSITION_ONLY})
        record_parse_result(session, company, 2024, stats, committed=False)
        gate = year_review_gate(session, company, 2024)
        # Các check đọc m15/production_out_qty: C2.1 (tổng), C4.3, C5.1 (riêng lẻ).
        assert gate.check_codes == ["C2.1", "C4.3", "C5.1"]

    def test_review_gate_for_files_none_when_all_verified(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        record_parse_result(session, company, 2024, _m15_stats(company.code), committed=False)
        rows = session.query(DataFile).filter_by(company_id=company.id).all()
        assert review_gate_for_files(rows) is None


class TestDecisionHook:
    def test_no_gate_advances(self):
        assert should_stop_for_review(None) is False

    def test_gate_stops(self, session, company, tmp_path):
        _seed_m15(session, company, tmp_path)
        stats = _m15_stats(company.code, evidence={"production_out_qty": POSITION_ONLY})
        record_parse_result(session, company, 2024, stats, committed=False)
        gate = year_review_gate(session, company, 2024)
        assert should_stop_for_review(gate) is True

    def test_saved_map_advances_despite_gate(self, session, company, tmp_path):
        # Hook WS1-3 (#6): map đã lưu khớp file → coi verified → tự advance dù có gate.
        _seed_m15(session, company, tmp_path)
        stats = _m15_stats(company.code, evidence={"production_out_qty": POSITION_ONLY})
        record_parse_result(session, company, 2024, stats, committed=False)
        gate = year_review_gate(session, company, 2024)
        assert gate is not None
        assert should_stop_for_review(gate, has_saved_map=True) is False
