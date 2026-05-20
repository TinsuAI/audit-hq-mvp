from pathlib import Path

import pytest

from app.pipeline.discover import _pick_best, discover

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

pytestmark = pytest.mark.skipif(
    not DATA_ROOT.exists(),
    reason="Dữ liệu thực không có sẵn",
)


def test_discover_hong_an_2024():
    res = discover("HONG_AN", 2024, DATA_ROOT)
    assert res.m15 is not None and "NVL" in res.m15.name
    assert res.m15a is not None and "SP" in res.m15a.name
    assert res.m16 is not None and res.m16.name.lower().startswith(("bcdm", "dinhmuc"))
    assert res.bcct is not None and "HangChiTiet" in res.bcct.name


def test_pick_best_prefers_non_draft(tmp_path: Path):
    a = tmp_path / "BCQT.xlsx"
    b = tmp_path / "BCQT draft.xlsx"
    c = tmp_path / "BCQT__dup1.xlsx"
    for p in (a, b, c):
        p.write_bytes(b"x")
    chosen = _pick_best([a, b, c])
    assert chosen == a


def test_pick_best_prefers_xlsx_over_xls(tmp_path: Path):
    a = tmp_path / "BCQT.xls"
    b = tmp_path / "BCQT.xlsx"
    for p in (a, b):
        p.write_bytes(b"x")
    chosen = _pick_best([a, b])
    assert chosen == b
