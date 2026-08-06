"""Migration f1c4a2b7d3e5 trên DB ĐÃ CÓ dữ liệu — `companies` là đích của 14 khoá ngoại.

DB rỗng không chứng minh gì: `batch_alter_table` dựng lại bảng bằng DROP + CREATE, chỉ hỏng khi
bảng đích đã có dòng con trỏ về. Test dựng DB tới revision trước, chèn 1 dòng `companies` cùng
dòng con ở 3 bảng có FK, rồi chạy upgrade và downgrade.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REV = "f1c4a2b7d3e5"
PREV = "c5d6e7f8a9b0"


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"alembic {' '.join(args)} lỗi:\n{r.stdout}\n{r.stderr}"


def _columns(db_path: Path, table: str) -> list[str]:
    with sqlite3.connect(db_path) as c:
        return [r[1] for r in c.execute(f"pragma table_info({table})")]


def _seed(db_path: Path) -> None:
    with sqlite3.connect(db_path) as c:
        c.execute("pragma foreign_keys=ON")
        c.execute("insert into companies (id, code, name, risk_score) values (1, 'DN_900', 'X', 0)")
        c.execute(
            "insert into company_periods (company_id, period_year, is_manual, data_version)"
            " values (1, 2025, 0, 0)"
        )
        c.execute(
            "insert into norms (company_id, period_year, product_code, material_code, norm_qty)"
            " values (1, 2025, 'SP1', 'NVL1', 1.5)"
        )
        c.execute(
            "insert into findings (company_id, period_year, check_code, severity, title, status)"
            " values (1, 2025, 'C4.3', 'critical', 'x', 'open')"
        )
        c.commit()


def _child_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as c:
        return {
            t: c.execute(f"select count(*) from {t} where company_id = 1").fetchone()[0]
            for t in ("company_periods", "norms", "findings")
        }


def test_upgrade_and_downgrade_on_populated_db(tmp_path):
    db = tmp_path / "populated.sqlite"
    _alembic(db, "upgrade", PREV)
    _seed(db)
    assert "first_bcqt_year" not in _columns(db, "companies")
    before = _child_counts(db)

    _alembic(db, "upgrade", REV)
    assert "first_bcqt_year" in _columns(db, "companies")
    with sqlite3.connect(db) as c:
        # Dòng cũ nhận NULL = "chưa biết", không phải 0.
        assert c.execute("select first_bcqt_year from companies where id = 1").fetchone()[0] is None
        assert c.execute("select count(*) from companies").fetchone()[0] == 1
        assert c.execute("pragma foreign_key_check").fetchall() == []
    assert _child_counts(db) == before

    _alembic(db, "downgrade", PREV)
    assert "first_bcqt_year" not in _columns(db, "companies")
    with sqlite3.connect(db) as c:
        assert c.execute("select count(*) from companies").fetchone()[0] == 1
        assert c.execute("pragma foreign_key_check").fetchall() == []
    assert _child_counts(db) == before
