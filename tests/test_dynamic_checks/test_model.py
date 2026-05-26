"""Tests — CheckDefinition model."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.check_definition import CheckDefinition, CheckStatus


def test_create_check_definition(session):
    cd = CheckDefinition(
        code="X.1",
        kind="threshold_compare",
        title="Test check",
        description="Mô tả kiểm tra",
        spec={"kind": "threshold_compare", "table": "nvl_balances"},
    )
    session.add(cd)
    session.commit()
    assert cd.id is not None
    assert cd.status == CheckStatus.DRAFT
    assert cd.group == 99


def test_code_unique(session):
    session.add(CheckDefinition(
        code="X.1", kind="threshold_compare", title="A", description="",
        spec={},
    ))
    session.commit()
    session.add(CheckDefinition(
        code="X.1", kind="threshold_compare", title="B", description="",
        spec={},
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_status_transitions(session):
    cd = CheckDefinition(code="X.1", kind="threshold_compare", title="T", description="", spec={})
    session.add(cd)
    session.commit()
    assert cd.status == CheckStatus.DRAFT
    cd.status = CheckStatus.PUBLISHED
    session.commit()
    session.refresh(cd)
    assert cd.status == CheckStatus.PUBLISHED


def test_spec_stored_as_json(session):
    spec = {
        "kind": "threshold_compare",
        "table": "nvl_balances",
        "subject_col": "material_code",
        "metric_col": "closing_qty",
        "thresholds": [{"lt": 0, "severity": "critical"}],
    }
    cd = CheckDefinition(code="X.1", kind="threshold_compare", title="T", description="", spec=spec)
    session.add(cd)
    session.commit()
    session.expire(cd)
    assert cd.spec["table"] == "nvl_balances"
    assert cd.spec["thresholds"][0]["severity"] == "critical"


def test_next_code(session):
    from app.models.check_definition import next_check_code
    assert next_check_code(session) == "X.1"
    session.add(CheckDefinition(code="X.1", kind="threshold_compare", title="T", description="", spec={}))
    session.commit()
    assert next_check_code(session) == "X.2"
    session.add(CheckDefinition(code="X.2", kind="threshold_compare", title="T2", description="", spec={}))
    session.commit()
    assert next_check_code(session) == "X.3"
