"""Tests — DynamicCheckRunner DSL 5 kinds.

Mỗi kind 1 fixture test + edge cases quan trọng.
Tất cả test chạy trên in-memory SQLite qua conftest `session` + `company`.
"""

from __future__ import annotations

import pytest

from app.checks.dynamic_runner import DynamicCheckRunner, SpecValidationError
from app.models import Finding
from tests.conftest import add_decl, add_nvl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(spec: dict, session, company_id: int, year: int = 2024) -> list[Finding]:
    runner = DynamicCheckRunner(code="X.1", spec=spec)
    return runner.run(session, company_id, year)


# ---------------------------------------------------------------------------
# kind = threshold_compare
# ---------------------------------------------------------------------------

class TestThresholdCompare:
    SPEC = {
        "kind": "threshold_compare",
        "table": "nvl_balances",
        "subject_col": "material_code",
        "metric_col": "closing_qty",
        "thresholds": [{"lt": 0, "severity": "critical"}],
        "title_template": "Tồn cuối {subject_key} âm ({value:.2f})",
    }

    def test_fires_when_below_threshold(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].subject_key == "NVL001"
        assert "NVL001" in findings[0].title

    def test_no_fire_when_above_threshold(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=10)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_multiple_rows_multiple_findings(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-1)
        add_nvl(session, company.id, material_code="NVL002", closing=-2)
        add_nvl(session, company.id, material_code="NVL003", closing=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 2

    def test_scoped_to_company(self, session, company):
        from app.models import Company
        other = Company(code="OTHER", name="Other DN")
        session.add(other)
        session.flush()
        add_nvl(session, other.id, material_code="NVL001", closing=-5)
        add_nvl(session, company.id, material_code="NVL002", closing=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_scoped_to_year(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-5, year=2023)
        add_nvl(session, company.id, material_code="NVL001", closing=5, year=2024)
        session.commit()
        findings = _run(self.SPEC, session, company.id, year=2024)
        assert findings == []

    def test_band_thresholds(self, session, company):
        spec = {
            **self.SPEC,
            "thresholds": [
                {"lt": 0, "severity": "critical"},
                {"lt": 5, "severity": "warning"},
                {"lt": 10, "severity": "info"},
            ],
        }
        add_nvl(session, company.id, material_code="NVL001", closing=-1)
        add_nvl(session, company.id, material_code="NVL002", closing=3)
        add_nvl(session, company.id, material_code="NVL003", closing=7)
        add_nvl(session, company.id, material_code="NVL004", closing=15)
        session.commit()
        findings = _run(spec, session, company.id)
        assert len(findings) == 3
        sev_map = {f.subject_key: f.severity for f in findings}
        assert sev_map["NVL001"] == "critical"
        assert sev_map["NVL002"] == "warning"
        assert sev_map["NVL003"] == "info"
        assert "NVL004" not in sev_map

    def test_gte_threshold(self, session, company):
        spec = {**self.SPEC, "thresholds": [{"gte": 100, "severity": "warning"}]}
        add_nvl(session, company.id, material_code="NVL001", closing=150)
        add_nvl(session, company.id, material_code="NVL002", closing=50)
        session.commit()
        findings = _run(spec, session, company.id)
        assert len(findings) == 1
        assert findings[0].subject_key == "NVL001"

    def test_range_band_and_semantics(self, session, company):
        """Band {gte: 5, lt: 20} phải AND-match: 5 ≤ value < 20."""
        spec = {
            **self.SPEC,
            "thresholds": [
                {"gte": 20, "severity": "critical"},
                {"gte": 5, "lt": 20, "severity": "warning"},
                {"gte": 0, "lt": 5, "severity": "info"},
            ],
        }
        add_nvl(session, company.id, material_code="N_CRIT", closing=100)
        add_nvl(session, company.id, material_code="N_WARN", closing=10)
        add_nvl(session, company.id, material_code="N_INFO", closing=3)
        add_nvl(session, company.id, material_code="N_NEG", closing=-1)  # không match band nào
        session.commit()
        findings = _run(spec, session, company.id)
        sev_map = {f.subject_key: f.severity for f in findings}
        assert sev_map.get("N_CRIT") == "critical"
        assert sev_map.get("N_WARN") == "warning"
        assert sev_map.get("N_INFO") == "info"
        assert "N_NEG" not in sev_map

    def test_check_code_in_finding(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-1)
        session.commit()
        runner = DynamicCheckRunner(code="X.7", spec=self.SPEC)
        findings = runner.run(session, company.id, 2024)
        assert findings[0].check_code == "X.7"

    def test_invalid_table_raises(self):
        with pytest.raises(SpecValidationError, match="table"):
            DynamicCheckRunner(code="X.1", spec={
                "kind": "threshold_compare",
                "table": "rm_rf_slash",  # not in whitelist
                "subject_col": "material_code",
                "metric_col": "closing_qty",
                "thresholds": [],
            })

    def test_invalid_column_raises(self):
        with pytest.raises(SpecValidationError, match="col"):
            DynamicCheckRunner(code="X.1", spec={
                "kind": "threshold_compare",
                "table": "nvl_balances",
                "subject_col": "material_code",
                "metric_col": "os.system('rm -rf /')",
                "thresholds": [],
            })


# ---------------------------------------------------------------------------
# kind = presence_check
# ---------------------------------------------------------------------------

class TestPresenceCheck:
    SPEC = {
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
    }

    def test_fires_when_a_not_in_b(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=10)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].subject_key == "NVL001"
        assert findings[0].severity == "critical"

    def test_no_fire_when_in_b(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=10)
        add_decl(session, company.id, declaration_no="D001", customs_code="E11",
                 item_code="NVL001", quantity=10)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_filter_a_applied(self, session, company):
        # import_qty=0 → filter_a loại ra → no finding
        add_nvl(session, company.id, material_code="NVL001", imported=0, closing=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_b_not_in_a_mode(self, session, company):
        """BCCT có tờ khai nhưng không có trong M15."""
        spec = {
            **self.SPEC,
            "mode": "b_not_in_a",
            "filter_a": {},
            "title_template": "Tờ khai {subject_key} không có trong M15",
        }
        add_decl(session, company.id, declaration_no="D001", customs_code="E11",
                 item_code="NVL_MISSING", quantity=10)
        session.commit()
        findings = _run(spec, session, company.id)
        assert len(findings) == 1
        assert findings[0].subject_key == "NVL_MISSING"

    def test_scoped_to_company(self, session, company):
        from app.models import Company
        other = Company(code="OTHER2", name="Other")
        session.add(other)
        session.flush()
        add_nvl(session, other.id, material_code="NVL001", imported=10)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []


# ---------------------------------------------------------------------------
# kind = aggregate_threshold
# ---------------------------------------------------------------------------

class TestAggregateThreshold:
    SPEC = {
        "kind": "aggregate_threshold",
        "table": "nvl_balances",
        "subject_col": "material_code",
        "agg_fn": "sum",
        "metric_col": "closing_qty",
        "thresholds": [{"lt": 0, "severity": "critical"}],
        "title_template": "Tổng tồn cuối {subject_key} âm ({value:.2f})",
    }

    def test_sum_fires(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-3, year=2024)
        add_nvl(session, company.id, material_code="NVL001", closing=-2, year=2024)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].details["value"] == pytest.approx(-5)

    def test_sum_positive_no_fire(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=3, year=2024)
        add_nvl(session, company.id, material_code="NVL001", closing=-2, year=2024)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_count_agg(self, session, company):
        spec = {
            **self.SPEC,
            "agg_fn": "count",
            "thresholds": [{"gte": 2, "severity": "info"}],
        }
        add_nvl(session, company.id, material_code="NVL001", closing=1)
        add_nvl(session, company.id, material_code="NVL001", closing=2)
        session.commit()
        findings = _run(spec, session, company.id)
        assert len(findings) == 1
        assert findings[0].details["value"] == 2

    def test_groups_by_subject(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", closing=-1)
        add_nvl(session, company.id, material_code="NVL002", closing=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].subject_key == "NVL001"


# ---------------------------------------------------------------------------
# kind = cross_table_match
# ---------------------------------------------------------------------------

class TestCrossTableMatch:
    SPEC = {
        "kind": "cross_table_match",
        "table_a": "nvl_balances",
        "join_col_a": "material_code",
        "agg_fn_a": "sum",
        "metric_col_a": "import_qty",
        "filter_a": {},
        "table_b": "declaration_lines",
        "join_col_b": "item_code",
        "agg_fn_b": "sum",
        "metric_col_b": "quantity",
        "filter_b": {"customs_code__in": ["E11", "E15"]},
        # lt-ascending bands (first-match wins): < 5% → no fire, 5-20% → info, ≥ 20% → warning
        "diff_thresholds": [
            {"lt": 5, "severity": None},
            {"lt": 20, "severity": "info"},
            {"gte": 20, "severity": "warning"},
        ],
        "title_template": "Lệch nhập {subject_key}: M15={val_a:.2f} BCCT={val_b:.2f} ({pct:.1f}%)",
    }

    def test_no_diff_no_finding(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E11",
                 item_code="NVL001", quantity=100)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_diff_below_threshold_no_finding(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E11",
                 item_code="NVL001", quantity=103)  # 3% diff < 5%
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_diff_info(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E11",
                 item_code="NVL001", quantity=110)  # 10% diff
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].severity == "info"

    def test_diff_warning(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E11",
                 item_code="NVL001", quantity=130)  # 30% diff
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_filter_b_applied(self, session, company):
        """customs_code E21 (not in filter) → không tính vào BCCT."""
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E21",
                 item_code="NVL001", quantity=100)  # filtered out
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        # BCCT sum=0, M15 sum=100 → 100% diff → warning
        assert len(findings) == 1

    def test_details_contain_values(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100)
        add_decl(session, company.id, declaration_no="D1", customs_code="E11",
                 item_code="NVL001", quantity=130)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        d = findings[0].details
        assert "val_a" in d
        assert "val_b" in d
        assert "pct" in d


# ---------------------------------------------------------------------------
# kind = ratio_threshold
# ---------------------------------------------------------------------------

class TestRatioThreshold:
    SPEC = {
        "kind": "ratio_threshold",
        "table": "nvl_balances",
        "subject_col": "material_code",
        "numerator_col": "repurpose_qty",
        "denominator_col": "import_qty",
        "scale_pct": True,
        # lt-ascending bands: < 10% → no fire, 10-25% → warning, ≥ 25% → critical
        "thresholds": [
            {"lt": 10, "severity": None},
            {"lt": 25, "severity": "warning"},
            {"gte": 25, "severity": "critical"},
        ],
        "title_template": "Tỷ lệ chuyển MĐSD {subject_key}: {value:.1f}%",
    }

    def test_no_fire_below_threshold(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100, repurpose=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_warning(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100, repurpose=15)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_critical(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100, repurpose=30)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_zero_denominator_skipped(self, session, company):
        """import_qty=0 → ratio undefined → skip (no finding)."""
        add_nvl(session, company.id, material_code="NVL001", imported=0, repurpose=5)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings == []

    def test_details_contain_value(self, session, company):
        add_nvl(session, company.id, material_code="NVL001", imported=100, repurpose=30)
        session.commit()
        findings = _run(self.SPEC, session, company.id)
        assert findings[0].details["value"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestSpecValidation:
    def test_unknown_kind_raises(self):
        with pytest.raises(SpecValidationError, match="kind"):
            DynamicCheckRunner(code="X.1", spec={"kind": "magic_check"})

    def test_missing_required_field_raises(self):
        with pytest.raises(SpecValidationError):
            DynamicCheckRunner(code="X.1", spec={
                "kind": "threshold_compare",
                # missing table, subject_col, metric_col, thresholds
            })

    def test_invalid_agg_fn_raises(self):
        with pytest.raises(SpecValidationError, match="agg_fn"):
            DynamicCheckRunner(code="X.1", spec={
                "kind": "aggregate_threshold",
                "table": "nvl_balances",
                "subject_col": "material_code",
                "agg_fn": "exec",  # not in whitelist
                "metric_col": "closing_qty",
                "thresholds": [],
            })
