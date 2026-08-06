"""Đoán `first_bcqt_year` — chỉ đọc bảng quyết toán, chỉ điền chỗ trống."""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.models import Company
from scripts.seed_first_bcqt_year import main
from tests.conftest import add_decl, add_norm, add_nvl


@pytest.fixture
def prod_like():
    import app.database as dbmod

    eng = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    ses = dbmod.sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    dbmod.engine, dbmod.SessionLocal = eng, ses
    Base.metadata.create_all(eng)
    yield ses
    eng.dispose()
    dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def _company(ses, code: str, tax_id: str, **kw) -> int:
    with ses() as s:
        c = Company(code=code, tax_id=tax_id, name=code, **kw)
        s.add(c)
        s.commit()
        return c.id


def test_guesses_the_earliest_settlement_year(prod_like):
    cid = _company(prod_like, "DN_A", "1")
    with prod_like() as s:
        add_nvl(s, cid, material_code="A", year=2024)
        add_norm(s, cid, product_code="TP", material_code="A", norm_qty=1.0, year=2022)
        s.commit()

    assert main([]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year == 2022


def test_declarations_alone_do_not_count(prod_like):
    """Tờ khai không phải báo cáo quyết toán — cửa sổ tờ khai còn rộng hơn."""
    cid = _company(prod_like, "DN_B", "2")
    with prod_like() as s:
        add_decl(s, cid, declaration_no="1", customs_code="E31",
                 item_code="X", quantity=1, year=2019)
        add_nvl(s, cid, material_code="A", year=2024)
        s.commit()

    assert main([]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year == 2024


def test_leaves_an_existing_value_alone_unless_overwrite(prod_like):
    cid = _company(prod_like, "DN_C", "3", first_bcqt_year=2018)
    with prod_like() as s:
        add_nvl(s, cid, material_code="A", year=2024)
        s.commit()

    assert main([]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year == 2018

    assert main(["--overwrite"]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year == 2024


def test_report_mode_writes_nothing(prod_like):
    cid = _company(prod_like, "DN_D", "4")
    with prod_like() as s:
        add_nvl(s, cid, material_code="A", year=2024)
        s.commit()

    assert main(["--report"]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year is None


def test_company_without_settlement_data_is_skipped(prod_like):
    cid = _company(prod_like, "DN_E", "5")
    assert main([]) == 0
    with prod_like() as s:
        assert s.get(Company, cid).first_bcqt_year is None
