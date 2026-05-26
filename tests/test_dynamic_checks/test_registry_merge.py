"""Tests — registry merge helper (Luồng A)."""

from __future__ import annotations

from app.checks.registry import SPECS, Severity, get_all_specs, get_check_meta
from app.models.check_definition import CheckDefinition, CheckStatus


def test_get_check_meta_builtin(session):
    """Built-in check trả về CheckSpec đúng."""
    meta = get_check_meta("C1.1", session)
    assert meta is not None
    assert meta.code == "C1.1"
    assert meta.title == SPECS["C1.1"].title


def test_get_check_meta_unknown(session):
    """Code không tồn tại trả về None."""
    assert get_check_meta("ZZZZ", session) is None


def test_get_check_meta_dynamic(session):
    """Check động đã publish trả về CheckSpec tổng hợp từ DB."""
    cd = CheckDefinition(
        code="X.1",
        kind="threshold_compare",
        title="Tồn cuối âm mở rộng",
        description="Mô tả",
        spec={"kind": "threshold_compare"},
        status=CheckStatus.PUBLISHED,
        group=99,
        default_severity="critical",
    )
    session.add(cd)
    session.commit()

    meta = get_check_meta("X.1", session)
    assert meta is not None
    assert meta.code == "X.1"
    assert meta.title == "Tồn cuối âm mở rộng"
    assert meta.group == 99
    assert meta.default_severity == Severity.CRITICAL


def test_get_check_meta_dynamic_draft_excluded(session):
    """Draft check không expose qua get_check_meta."""
    cd = CheckDefinition(
        code="X.1", kind="threshold_compare", title="T", description="",
        spec={}, status=CheckStatus.DRAFT,
    )
    session.add(cd)
    session.commit()
    assert get_check_meta("X.1", session) is None


def test_get_all_specs_includes_builtin(session):
    """get_all_specs trả về dict chứa tất cả built-in SPECS."""
    all_specs = get_all_specs(session)
    for code in SPECS:
        assert code in all_specs


def test_get_all_specs_includes_published_dynamic(session):
    """get_all_specs gộp built-in + published dynamic checks."""
    cd = CheckDefinition(
        code="X.1", kind="threshold_compare", title="Dynamic T", description="",
        spec={}, status=CheckStatus.PUBLISHED,
    )
    session.add(cd)
    session.commit()

    all_specs = get_all_specs(session)
    assert "X.1" in all_specs
    assert all_specs["X.1"].title == "Dynamic T"


def test_get_all_specs_excludes_draft(session):
    """Draft checks không xuất hiện trong get_all_specs."""
    cd = CheckDefinition(
        code="X.99", kind="threshold_compare", title="Draft", description="",
        spec={}, status=CheckStatus.DRAFT,
    )
    session.add(cd)
    session.commit()
    all_specs = get_all_specs(session)
    assert "X.99" not in all_specs


def test_get_all_specs_excludes_disabled(session):
    """Disabled checks không xuất hiện trong get_all_specs."""
    cd = CheckDefinition(
        code="X.99", kind="threshold_compare", title="Disabled", description="",
        spec={}, status=CheckStatus.DISABLED,
    )
    session.add(cd)
    session.commit()
    all_specs = get_all_specs(session)
    assert "X.99" not in all_specs
