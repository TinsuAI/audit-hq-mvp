from pathlib import Path

import pytest

from app.pipeline.discover import _pick_all, _pick_best, discover

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
    assert res.bcct and any("HangChiTiet" in p.name for p in res.bcct)


def test_discover_hong_an_2021_loads_both_nk_and_xk():
    # 2021 tách tờ khai nhập (NK) và xuất (XK) thành 2 file — phải nạp cả hai.
    res = discover("HONG_AN", 2021, DATA_ROOT)
    names = [p.name for p in res.bcct]
    assert any("NK" in n for n in names), names
    assert any(".XK" in n or " XK" in n for n in names), names


def test_pick_all_keeps_non_draft_combines_multiple(tmp_path: Path):
    nk = tmp_path / "BaoCaoHangChiTiet.NK 2021.xls"
    xk = tmp_path / "BaoCaoHangChiTiet.XK 2021.xls"
    dup = tmp_path / "BaoCaoHangChiTiet.XK 2021__dup1.xls"
    for p in (nk, xk, dup):
        p.write_bytes(b"x")
    chosen = _pick_all([nk, xk, dup])
    assert set(chosen) == {nk, xk}  # cả NK lẫn XK, loại dup


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
