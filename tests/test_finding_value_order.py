"""Bảng phát hiện xếp theo giá trị tiền, không theo mã (sổ yêu cầu 3.1, 4.1).

Xếp theo mã thì mã có chênh lệch lớn nhất nằm ở trang bất kỳ — cán bộ phải đọc hết
mới thấy. Xếp bằng SQL chứ không xếp trong Python: bảng phân trang, xếp sau khi cắt
trang chỉ xếp trong phạm vi một trang.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding


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
        c = Company(code="DN_VAL", tax_id="9999999999", name="DN xếp theo tiền")
        db.add(c)
        db.flush()
        # Mã theo bảng chữ cái đi NGƯỢC thứ tự tiền, để phân biệt hai cách xếp.
        for code, value in (("AAA", 1_000.0), ("BBB", 900_000_000.0),
                            ("CCC", None), ("DDD", 5_000_000.0)):
            db.add(Finding(
                company_id=c.id, period_year=2024, check_code="C1.1",
                severity="critical", subject_type="material_code",
                subject_key=code, value_vnd=value,
                title=f"Lệch nhập NVL {code}",
            ))
        db.commit()
    return eng, ses


def _teardown(eng):
    eng.dispose()
    import app.database as dbmod
    dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def test_findings_are_ranked_by_money_with_unpriced_last():
    eng, _ = _setup()
    try:
        with TestClient(app) as client:
            client.post("/login", data={"user": "admin", "password": "admin"},
                        follow_redirects=False)
            html = client.get("/companies/DN_VAL?year=2024&check=C1.1").text
    finally:
        _teardown(eng)

    order = [m for m in re.findall(r"\b(AAA|BBB|CCC|DDD)\b", html)]
    seen = list(dict.fromkeys(order))
    # BBB (900 triệu) → DDD (5 triệu) → AAA (1 nghìn) → CCC (chưa quy ra tiền).
    assert seen == ["BBB", "DDD", "AAA", "CCC"]
