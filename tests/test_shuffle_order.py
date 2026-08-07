"""Ràng buộc hợp đồng của `--shuffle-seed`: cùng seed thì cùng thứ tự.

Nếu bài này đỏ thì một lượt chạy đỏ không tái hiện lại được bằng seed in ra,
tức là cả cơ chế xáo thứ tự mất tác dụng.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.conftest import _shuffled_order


@dataclass
class _FakeItem:
    nodeid: str


def _items() -> list[_FakeItem]:
    ids = []
    for module in ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py"):
        for name in ("test_one", "test_two", "test_three"):
            ids.append(f"{module}::{name}")
        for name in ("test_x", "test_y"):
            ids.append(f"{module}::TestGroup::{name}")
    return [_FakeItem(nodeid=i) for i in ids]


def test_cung_seed_cho_cung_thu_tu():
    a = [i.nodeid for i in _shuffled_order(_items(), 12345)]
    b = [i.nodeid for i in _shuffled_order(_items(), 12345)]
    assert a == b


def test_khac_seed_cho_khac_thu_tu():
    a = [i.nodeid for i in _shuffled_order(_items(), 1)]
    b = [i.nodeid for i in _shuffled_order(_items(), 2)]
    assert a != b


def test_khong_mat_khong_nhan_ban_item():
    original = [i.nodeid for i in _items()]
    shuffled = [i.nodeid for i in _shuffled_order(_items(), 99)]
    assert sorted(shuffled) == sorted(original)


def test_item_cung_module_nam_lien_nhau():
    """Fixture `scope="module"` chỉ đúng khi item cùng module không bị xen kẽ."""
    order = [i.nodeid.split("::")[0] for i in _shuffled_order(_items(), 777)]
    seen: list[str] = []
    for module in order:
        if not seen or seen[-1] != module:
            assert module not in seen, f"module {module} bị tách thành nhiều đoạn"
            seen.append(module)


def test_item_cung_class_nam_lien_nhau():
    order = [i.nodeid for i in _shuffled_order(_items(), 4242)]
    positions = [n for n, nodeid in enumerate(order) if "::TestGroup::" in nodeid]
    by_module: dict[str, list[int]] = {}
    for pos in positions:
        by_module.setdefault(order[pos].split("::")[0], []).append(pos)
    for module, idx in by_module.items():
        assert idx == list(range(idx[0], idx[0] + len(idx))), f"class ở {module} bị tách rời"
