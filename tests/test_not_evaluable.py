"""T2 (#58) — `not_evaluable` là trạng thái chạy thật.

Ba mặt:
- GHI: check trả `NotEvaluable(reason, remedy=...)` → `check_runs.status` +
  `.status_reason` + `.remedy` (lớp cách gỡ, #82).
- ĐIỂM: mã đó bị loại khỏi CẢ `rule_scores` LẪN `max_raw`. Nghiệm thu: điểm và hạng
  bằng đúng lần chạy mà mã đó không có trong tập luật, KHÔNG so với số cứng.
- UI: phân biệt "đã đánh giá, 0 phát hiện" với "chưa đánh giá được", kèm lý do.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.checks.denominators import RULE_SCOPE
from app.checks.not_evaluable import (
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    STATUS_NOT_EVALUABLE,
    NotEvaluable,
    load_not_evaluable,
    truncate_reason,
)
from app.checks.scoring import compute_company_year_score
from app.main import app
from app.models import CheckRun, Company, CompanyYearScore, Finding
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl

REASON = "Kỳ sớm nhất của DN, chưa biết năm đầu nộp BCQT."
GATED_CODE = "C4.3"


def _make_finding(check_code: str, severity: str, subject_key: str) -> Finding:
    return Finding(
        company_id=1, period_year=2024, check_code=check_code, severity=severity,
        subject_type="material_code", subject_key=subject_key, status="new", title="x",
    )


# --- Khai báo ---


def test_not_evaluable_requires_reason():
    with pytest.raises(ValueError):
        NotEvaluable("", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)
    with pytest.raises(ValueError):
        NotEvaluable("   ", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)


def test_truncate_reason_fits_column():
    assert len(truncate_reason("x" * 400)) == 255


# --- Ghi vào check_runs ---


def _patch_checks(monkeypatch, *, code: str, result_fn, in_scope: bool) -> None:
    """Thay ALL_CHECKS + RULE_SCOPE cho một lần chạy.

    `result_fn=None` → mã vắng mặt hoàn toàn (không chạy, không nằm trong tập luật).
    """
    import app.checks.denominators as denom_mod
    import app.pipeline.run_checks as rc_mod

    checks = dict(rc_mod.ALL_CHECKS)
    scope = dict(RULE_SCOPE)
    if result_fn is None:
        checks.pop(code, None)
    else:
        checks[code] = result_fn
    if not in_scope:
        scope.pop(code, None)
    monkeypatch.setattr(rc_mod, "ALL_CHECKS", checks)
    monkeypatch.setattr(denom_mod, "RULE_SCOPE", scope)



def _load_every_source(session, company_id: int, year: int = 2024) -> None:
    """Nạp đủ bcct/m15/m15a/m16 để cổng nguồn (#53) không chặn check nào.

    Các test trong nhóm này đo đường `NotEvaluable` do chính check trả về. Không có
    dòng nguồn thì cổng nguồn chặn TOÀN BỘ check trước khi dispatch và mã đang đo
    không bao giờ chạy — hai cổng dùng chung một trạng thái nên fixture phải nói rõ
    đang đo cổng nào.
    """
    from app.models import Norm
    from tests.conftest import add_decl, add_sp

    add_nvl(session, company_id, material_code="SRC", imported=1, closing=1, year=year)
    # C6.1 tự trả `NotEvaluable` khi thiếu M15 kỳ N-1. Nạp kỳ trước với tồn cuối = 0
    # (khớp tồn đầu kỳ này) để nó chạy được mà không sinh phát hiện — nếu không, mọi
    # test dưới đây đo lẫn một mã `not_evaluable` thứ hai không liên quan.
    add_nvl(session, company_id, material_code="SRC", closing=0, year=year - 1)
    add_sp(session, company_id, product_code="SRC_P", export_qty=1, closing=0, year=year)
    # Y hệt cho C6.2 trên Mẫu 15a — nó có cổng kỳ trước riêng, Mẫu 15 kỳ trước không mở.
    add_sp(session, company_id, product_code="SRC_P", closing=0, year=year - 1)
    session.add(Norm(company_id=company_id, period_year=year, product_code="SRC_P",
                     material_code="SRC", norm_qty=1.0))
    add_decl(session, company_id, declaration_no="SRC1", customs_code="E31",
             item_code="SRC", quantity=1, year=year)
    session.commit()


def _not_evaluable_check(_session, _company_id, _year):
    # Lý do là ca kỳ biên → lớp cách gỡ 2 (cần kỳ khác hoặc một xác nhận).
    return NotEvaluable(REASON, remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)


def _clean_check(_session, _company_id, _year):
    return []


def test_run_checks_persists_status_and_reason(session, company, monkeypatch):
    _load_every_source(session, company.id)
    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)

    stats = run_checks(company.code, 2024, session=session)

    assert stats.not_evaluable == {GATED_CODE: REASON}
    row = session.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id,
            CheckRun.period_year == 2024,
            CheckRun.check_code == GATED_CODE,
        )
    )
    assert row.status == STATUS_NOT_EVALUABLE
    assert row.status_reason == REASON
    assert row.finding_count == 0
    # Check bình thường vẫn 'ok' và không có lý do.
    ok_row = session.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id,
            CheckRun.period_year == 2024,
            CheckRun.check_code == "C1.1",
        )
    )
    assert ok_row.status == "ok"
    assert ok_row.status_reason is None


def test_rerun_ok_clears_previous_reason(session, company, monkeypatch):
    _load_every_source(session, company.id)
    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)
    run_checks(company.code, 2024, session=session)

    # Lần sau đủ đầu vào → trạng thái phải trở lại 'ok', lý do cũ không được ở lại.
    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_clean_check, in_scope=True)
    run_checks(company.code, 2024, session=session)

    row = session.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id, CheckRun.check_code == GATED_CODE,
        )
    )
    assert row.status == "ok"
    assert row.status_reason is None
    assert load_not_evaluable(session, company.id, 2024) == {}


# --- Điểm rủi ro: loại khỏi cả tử số lẫn trần ---


def test_scoring_not_evaluable_equals_rule_absent_from_scope():
    """Nghiệm thu (hàm thuần): so hai kịch bản với nhau, không so số cứng."""
    findings = [_make_finding("C1.1", "critical", f"MAT{i}") for i in range(4)]
    denoms = {"nvl": 10, "tp": 10, "m16": 10}
    scope_absent = {c: sc for c, sc in RULE_SCOPE.items() if c != GATED_CODE}

    gated = compute_company_year_score(
        findings, denoms, rule_scope=dict(RULE_SCOPE), not_evaluable={GATED_CODE},
    )
    absent = compute_company_year_score(findings, denoms, rule_scope=scope_absent)

    assert gated["score"] == absent["score"]
    assert gated["tier"] == absent["tier"]
    assert gated["max_raw"] == absent["max_raw"]
    assert gated["not_evaluable"] == [GATED_CODE]


def test_scoring_ceiling_shrinks_so_missing_data_does_not_flatter():
    """Chỉ bỏ điểm cộng mà giữ trần thì dữ liệu thiếu làm điểm đẹp lên."""
    findings = [_make_finding("C1.1", "critical", f"MAT{i}") for i in range(4)]
    denoms = {"nvl": 10, "tp": 10, "m16": 10}

    gated = compute_company_year_score(
        findings, denoms, rule_scope=dict(RULE_SCOPE), not_evaluable={GATED_CODE},
    )
    # Cùng dữ liệu nhưng C4.3 vẫn nằm trong trần (đúng cách hệ thống ứng xử với một
    # check chạy ra 0 phát hiện) → mẫu số lớn hơn → điểm thấp hơn.
    kept_in_ceiling = compute_company_year_score(
        findings, denoms, rule_scope=dict(RULE_SCOPE),
    )
    assert gated["max_raw"] == kept_in_ceiling["max_raw"] - 10
    assert gated["score"] > kept_in_ceiling["score"]


def test_scoring_drops_stale_findings_of_gated_rule():
    findings = [
        _make_finding("C1.1", "critical", "MAT1"),
        _make_finding(GATED_CODE, "critical", "MAT2"),
    ]
    denoms = {"nvl": 10, "tp": 10, "m16": 10}
    gated = compute_company_year_score(
        findings, denoms, rule_scope=dict(RULE_SCOPE), not_evaluable={GATED_CODE},
    )
    assert GATED_CODE not in gated["rule_scores"]


# --- Nghiệm thu ticket: CompanyYearScore.score + tier ---


def _seed(session, code: str) -> Company:
    c = Company(code=code, tax_id=f"99999{code[-1]}", name=f"DN {code}", address="Hà Nội")
    session.add(c)
    session.flush()
    for i in range(6):
        add_nvl(
            session, c.id, material_code=f"MAT{i}", opening=10, imported=100,
            production_out=200, closing=-5,
        )
    session.commit()
    _load_every_source(session, c.id)
    return c


def _year_score(session, company_id: int) -> CompanyYearScore:
    return session.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company_id,
            CompanyYearScore.period_year == 2024,
        )
    )


def test_gated_check_leaves_score_and_tier_identical_to_absent_check(session, monkeypatch):
    """Nghiệm thu #58: `not_evaluable` == mã đó vắng mặt hoàn toàn khỏi lần chạy.

    Hai DN dữ liệu giống hệt nhau: một DN chạy C4.3 trả `NotEvaluable`, DN kia không
    có C4.3 trong tập luật. `score` và `tier` phải bằng nhau — so trực tiếp hai kịch
    bản, không so với số cứng.
    """
    gated_co = _seed(session, "DN_GATED")
    absent_co = _seed(session, "DN_ABSENT")

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)
    run_checks(gated_co.code, 2024, session=session)

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=None, in_scope=False)
    run_checks(absent_co.code, 2024, session=session)

    gated, absent = _year_score(session, gated_co.id), _year_score(session, absent_co.id)
    assert gated.score > 0, "fixture phải sinh điểm khác 0 thì phép so mới có nghĩa"
    assert gated.score == absent.score
    assert gated.tier == absent.tier
    assert gated.breakdown["max_raw"] == absent.breakdown["max_raw"]
    assert gated.breakdown["not_evaluable"] == [GATED_CODE]


def test_gated_check_scores_higher_than_same_check_reporting_zero(session, monkeypatch):
    """DN có dữ liệu thiếu KHÔNG được điểm đẹp hơn DN đã đánh giá sạch bài đó."""
    gated_co = _seed(session, "DN_GATED2")
    clean_co = _seed(session, "DN_CLEAN2")

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)
    run_checks(gated_co.code, 2024, session=session)

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_clean_check, in_scope=True)
    run_checks(clean_co.code, 2024, session=session)

    assert _year_score(session, gated_co.id).score > _year_score(session, clean_co.id).score


def test_partial_rerun_keeps_gated_state_of_other_checks(session, company, monkeypatch):
    """Chạy lẻ một mã không được kéo mã `not_evaluable` khác về lại mẫu số."""
    for i in range(6):
        add_nvl(session, company.id, material_code=f"MAT{i}", opening=10, imported=100,
                production_out=200, closing=-5)
    session.commit()

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)
    run_checks(company.code, 2024, session=session)
    full = _year_score(session, company.id)
    score_after_full, max_raw_after_full = full.score, full.breakdown["max_raw"]

    run_checks(company.code, 2024, only={"C1.1"}, session=session)
    partial = _year_score(session, company.id)
    assert partial.score == score_after_full
    assert partial.breakdown["max_raw"] == max_raw_after_full


def test_recompute_after_status_change_keeps_gated_rule_out(session, company, monkeypatch):
    """Đổi trạng thái finding (recompute) cũng phải giữ mã `not_evaluable` ngoài trần."""
    from app.pipeline.recompute import recompute_company_year

    for i in range(6):
        add_nvl(session, company.id, material_code=f"MAT{i}", opening=10, imported=100,
                production_out=200, closing=-5)
    session.commit()
    _load_every_source(session, company.id)

    _patch_checks(monkeypatch, code=GATED_CODE, result_fn=_not_evaluable_check, in_scope=True)
    run_checks(company.code, 2024, session=session)
    before = _year_score(session, company.id).breakdown["max_raw"]

    cys = recompute_company_year(session, company.id, 2024)
    session.commit()
    assert cys.breakdown["max_raw"] == before
    assert cys.breakdown["not_evaluable"] == [GATED_CODE]


# --- UI: phân biệt "0 phát hiện" với "chưa đánh giá được" ---


def _seed_ui_db(app_db) -> None:
    from datetime import datetime

    with app_db.SessionLocal() as db:
        c = Company(code="DN_NE", tax_id="9999999999", name="DN cổng dữ liệu")
        db.add(c)
        db.flush()

        ran_at = datetime(2026, 8, 5, 9, 0, 0)
        db.add(CheckRun(
            company_id=c.id, period_year=2024, check_code=GATED_CODE, ran_at=ran_at,
            finding_count=0, status=STATUS_NOT_EVALUABLE, status_reason=REASON,
            data_version=1,
        ))
        # Đã đánh giá, 0 phát hiện — KHÔNG được hiện ở khối "chưa đánh giá được".
        db.add(CheckRun(
            company_id=c.id, period_year=2024, check_code="C5.1", ran_at=ran_at,
            finding_count=0, status="ok", data_version=1,
        ))
        db.add(CompanyYearScore(
            company_id=c.id, period_year=2024, score=0, tier="Dữ liệu nhất quán",
            breakdown={
                "score": 0, "tier": "Dữ liệu nhất quán", "rule_scores": {},
                "combo_bonus": 0, "raw": 0, "max_raw": 180,
                "denominators": {"nvl": 3, "tp": 0, "m16": 0},
                "not_evaluable": [GATED_CODE],
            },
        ))
        db.commit()


def test_company_page_shows_not_evaluable_with_reason(app_db):
    _seed_ui_db(app_db)

    # `with TestClient(...)` chạy lifespan → `app/main.py` dựng JobWorker và gọi
    # `recover_zombie_jobs` qua `SessionLocal` của chính nó. `app_db` đã trỏ tên đó
    # vào DB tạm, nên vòng đời này không đụng hàng đợi thật của máy dev.
    with TestClient(app) as client:
        client.post("/login", data={"user": "admin", "password": "admin"},
                    follow_redirects=False)
        html = client.get("/companies/DN_NE?year=2024").text

    assert "Chưa đánh giá được" in html
    assert REASON in html
    assert GATED_CODE in html
    # Check 'ok' 0 phát hiện không bị gán nhãn chưa đánh giá được.
    ne_block = html.split("Chưa đánh giá được", 1)[1].split("</section>", 1)[0]
    assert "C5.1" not in ne_block
