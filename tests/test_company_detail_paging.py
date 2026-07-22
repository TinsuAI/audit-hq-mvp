"""Trang DN không được đổ hết phát hiện ra một trang.

Một DN thật sinh 11.003 phát hiện cho một kỳ; render hết là 18,7 MB HTML.
Trang tổng chỉ xem trước vài dòng mỗi kiểm tra, phần còn lại mở riêng có phân trang.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding
from app.routes.companies import _PAGE_SIZE, _PREVIEW_PER_GROUP

N_FINDINGS = _PREVIEW_PER_GROUP + _PAGE_SIZE + 7  # đủ để tràn sang trang 2


def _setup():
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    eng = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    ses = dbmod.sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    dbmod.engine, dbmod.SessionLocal = eng, ses
    Base.metadata.create_all(eng)
    with ses() as db:
        seed_default_admin(db, "admin", "admin")
        c = Company(code="DN_BIG", tax_id="9999999999", name="DN nhiều phát hiện")
        db.add(c)
        db.flush()
        for i in range(N_FINDINGS):
            db.add(Finding(
                company_id=c.id, period_year=2024, check_code="C1.6",
                severity="critical", subject_type="material_code",
                subject_key=f"MAT{i:05d}", title=f"NVL MAT{i:05d} chuyển MĐSD",
            ))
        db.commit()
    return eng, ses


def _teardown(eng):
    eng.dispose()
    import app.database as dbmod
    dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def test_overview_previews_and_drilldown_paginates():
    eng, _ = _setup()
    try:
        with TestClient(app) as client:
            client.post("/login", data={"user": "admin", "password": "admin"},
                        follow_redirects=False)

            overview = client.get("/companies/DN_BIG?year=2024").text
            # Tổng vẫn báo đủ, nhưng chỉ vẽ phần xem trước.
            assert f"{N_FINDINGS} phát hiện" in overview
            shown = set(re.findall(r"MAT\d{5}", overview))
            assert len(shown) == _PREVIEW_PER_GROUP
            assert f"Xem tất cả {N_FINDINGS} phát hiện" in overview
            assert "MAT00120" not in overview       # dòng cuối không nằm ở trang tổng

            p1 = client.get("/companies/DN_BIG?year=2024&check=C1.6").text
            assert "Trang 1/2" in p1
            assert "MAT00000" in p1

            p2 = client.get("/companies/DN_BIG?year=2024&check=C1.6&page=2").text
            assert "Trang 2/2" in p2
            assert "MAT00000" not in p2            # trang 2 là tập khác
            assert f"MAT{N_FINDINGS - 1:05d}" in p2
    finally:
        _teardown(eng)
