"""WS3 foundation — check_runs upsert trong run_checks + data_version.

- `run_checks` ghi 1 dòng `check_runs` mỗi (DN, năm, mã) cho MỌI check đã chạy, kể cả
  0 finding (nên KHÔNG suy từ `findings.created_at`).
- Latest-upsert: chạy lại dời `ran_at`, không append.
- `finding_count` khớp số finding thật; `data_version` = CompanyPeriod đọc ở đầu run.
- Chạy lẻ (`only=`) chỉ đụng check_runs của mã đó.
- Full run dọn check_runs orphan `X.*` đã gỡ công bố.
- `ingest()` bump `CompanyPeriod.data_version` trong transaction.
"""

from __future__ import annotations

import io
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.checks import ALL_CHECKS
from app.models import CheckRun, Company, CompanyPeriod, Finding
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl


def _check_runs(session, company_id, year=2024):
    return {
        r.check_code: r
        for r in session.scalars(
            select(CheckRun).where(
                CheckRun.company_id == company_id, CheckRun.period_year == year
            )
        ).all()
    }


def test_check_run_written_for_every_code_incl_zero_finding(session, company):
    run_checks(company.code, 2024, session=session)

    runs = _check_runs(session, company.id)
    # Mọi built-in check phải có dòng check_runs (kể cả check ra 0 finding).
    for code in ALL_CHECKS:
        assert code in runs, f"{code} thiếu dòng check_runs"
        assert runs[code].ran_at is not None
        assert runs[code].status == "ok"
    # Không có dòng COMBO_* (combo LOẠI khỏi check_runs).
    assert not any(c.startswith("COMBO_") for c in runs)


def test_finding_count_matches_actual(session, company):
    add_nvl(session, company.id, material_code="MAT_X", closing=-5)
    session.commit()

    run_checks(company.code, 2024, session=session)

    runs = _check_runs(session, company.id)
    for code, row in runs.items():
        actual = session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.company_id == company.id,
                Finding.period_year == 2024,
                Finding.check_code == code,
            )
        )
        assert row.finding_count == actual, f"{code}: {row.finding_count} != {actual}"


def test_latest_upsert_moves_ran_at_single_row(session, company):
    from datetime import datetime

    run_checks(company.code, 2024, session=session)

    # Đặt tay ran_at về quá khứ rồi chạy lại → phải dời lên, KHÔNG thêm dòng mới.
    row = _check_runs(session, company.id)["C1.1"]
    row.ran_at = datetime(2000, 1, 1)
    session.commit()

    run_checks(company.code, 2024, only={"C1.1"}, session=session)
    runs = session.scalars(
        select(CheckRun).where(
            CheckRun.company_id == company.id, CheckRun.check_code == "C1.1"
        )
    ).all()
    assert len(runs) == 1  # latest-upsert, không append
    assert runs[0].ran_at > datetime(2000, 1, 1)


def test_scoped_run_only_touches_that_code(session, company):
    run_checks(company.code, 2024, session=session)
    from datetime import datetime

    # Đóng băng ran_at của mọi dòng về mốc cũ.
    for r in _check_runs(session, company.id).values():
        r.ran_at = datetime(2000, 1, 1)
    session.commit()

    run_checks(company.code, 2024, only={"C1.1"}, session=session)

    runs = _check_runs(session, company.id)
    assert runs["C1.1"].ran_at > datetime(2000, 1, 1)  # đã chạy lại
    # Check khác giữ nguyên mốc cũ (không đụng).
    assert runs["C2.1"].ran_at == datetime(2000, 1, 1)


def test_data_version_recorded_from_company_period(session, company):
    session.add(
        CompanyPeriod(company_id=company.id, period_year=2024, data_version=7)
    )
    session.commit()

    run_checks(company.code, 2024, session=session)

    runs = _check_runs(session, company.id)
    assert all(r.data_version == 7 for r in runs.values())


def test_data_version_defaults_zero_without_company_period(session, company):
    run_checks(company.code, 2024, session=session)
    runs = _check_runs(session, company.id)
    assert all(r.data_version == 0 for r in runs.values())


def test_full_run_cleans_orphan_x_check_runs(session, company):
    from datetime import datetime

    # Dòng check_runs orphan cho check động đã gỡ công bố.
    session.add(CheckRun(
        company_id=company.id, period_year=2024, check_code="X.99",
        ran_at=datetime(2020, 1, 1), finding_count=3, status="ok", data_version=0,
    ))
    session.commit()

    run_checks(company.code, 2024, session=session)  # full run

    runs = _check_runs(session, company.id)
    assert "X.99" not in runs  # orphan bị dọn


def test_scoped_run_keeps_orphan_x_check_runs(session, company):
    """Chạy lẻ KHÔNG dọn orphan (chỉ full run dọn)."""
    from datetime import datetime

    session.add(CheckRun(
        company_id=company.id, period_year=2024, check_code="X.99",
        ran_at=datetime(2020, 1, 1), finding_count=3, status="ok", data_version=0,
    ))
    session.commit()

    run_checks(company.code, 2024, only={"C1.1"}, session=session)

    runs = _check_runs(session, company.id)
    assert "X.99" in runs  # chạy lẻ giữ nguyên


# ─────────────────────── ingest() bump data_version ───────────────────────

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _write_m15(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i in range(3):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())


def test_ingest_bumps_data_version(tmp_path):
    import app.pipeline.ingest as ingmod
    from app.database import Base, SessionLocal, engine
    from app.pipeline.ingest import ingest
    from app.settings import settings

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)
    try:
        _write_m15(tmp_path / "DN_DV/2024/BCQT/Mau15_NVL.xlsx")

        ingest("DN_DV", 2024, raw_root=tmp_path)
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_DV"))
            row = db.scalar(
                select(CompanyPeriod).where(
                    CompanyPeriod.company_id == c.id, CompanyPeriod.period_year == 2024
                )
            )
            assert row.data_version == 1

        ingest("DN_DV", 2024, raw_root=tmp_path)
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_DV"))
            row = db.scalar(
                select(CompanyPeriod).where(
                    CompanyPeriod.company_id == c.id, CompanyPeriod.period_year == 2024
                )
            )
            assert row.data_version == 2
    finally:
        settings.raw_data_path = prev_root
        new_engine.dispose()
        dbmod.engine = engine
        dbmod.SessionLocal = SessionLocal
        ingmod.SessionLocal = SessionLocal
