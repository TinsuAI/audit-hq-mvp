"""Bộ nhớ tạm phạm vi một lượt nạp — mỗi file chỉ mở MỘT lần.

Một lần tải lên chạy ba bước đọc cùng bộ file: chẩn đoán (`diagnose_upload`),
xem trước (`ingest(dry_run=True)`) rồi nạp thật (`ingest`). Trước đây mỗi bước
mở lại workbook từ đầu: BCCT 68MB của PILOT_006 mất 97 giây một lượt, nên một
lần tải lên ngốn hơn 6 phút và Cloudflare cắt kết nối ở 100 giây (lỗi 524).

Cache chỉ sống trong ``with parse_cache():`` — hết phạm vi thì thả, không giữ
kết quả parse (900MB cho một kỳ của 006) trong RAM giữa các job. Khoá gồm
``(mtime, size)`` nên file được tải lên đè sẽ parse lại chứ không trả bản cũ.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

# ContextVar chứ không phải biến module: worker job và worker AI là hai thread
# khác nhau, mỗi thread phải có phạm vi cache riêng.
_CACHE: ContextVar[dict[tuple, tuple[str, Any]] | None] = ContextVar(
    "parse_cache", default=None
)


@contextmanager
def parse_cache() -> Iterator[None]:
    """Mở phạm vi cache. Lồng nhau thì dùng chung phạm vi ngoài cùng."""
    if _CACHE.get() is not None:
        yield
        return
    token = _CACHE.set({})
    try:
        yield
    finally:
        _CACHE.reset(token)


def _map_key(officer_maps: dict[str, dict[str, Any]] | None) -> tuple:
    """Khoá theo NỘI DUNG map cột, không theo danh tính dict.

    Một lượt nạp nạp map cán bộ ở hai chỗ (trước phiên DB của `ingest`, rồi trong
    phiên khi lập kế hoạch theo sổ). Hai dict khác danh tính mà cùng nội dung phải
    trúng cùng một ô nhớ, nếu không mỗi file lại mở hai lần — đúng thứ ADR #24 sửa.

    Giá trị mỗi trường có thể là danh sách cột (bố cục mở rộng, #95) — đổi sang tuple
    thì khoá mới băm được.
    """
    if not officer_maps:
        return ()
    return tuple(
        (sig, tuple(sorted(
            (f, tuple(v) if isinstance(v, list | tuple) else v) for f, v in cols.items()
        )))
        for sig, cols in sorted(officer_maps.items())
    )


def memoize_parse(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Nhớ kết quả parse theo (hàm, đường dẫn, mtime, size, sheet, năm, map cán bộ).

    Ngoài phạm vi ``parse_cache()`` thì gọi thẳng — CLI và test không đổi hành vi.
    Lỗi cũng được nhớ: `SheetNotFound` là kết luận về file, không phải sự cố nhất
    thời, nên bước sau không cần mở lại file để nhận cùng lỗi đó.
    """

    @functools.wraps(fn)
    def wrapper(path, sheet=None, year=None, officer_maps=None):
        cache = _CACHE.get()
        if cache is None:
            return fn(path, sheet, year, officer_maps)
        try:
            st = Path(path).stat()
        except OSError:
            return fn(path, sheet, year, officer_maps)
        key = (
            fn.__name__, str(path), st.st_mtime_ns, st.st_size, sheet, year,
            _map_key(officer_maps),
        )
        hit = cache.get(key)
        if hit is None:
            try:
                hit = ("ok", fn(path, sheet, year, officer_maps))
            except Exception as e:  # noqa: BLE001 — nhớ lỗi để bước sau không mở lại file
                hit = ("err", e)
            cache[key] = hit
        kind, value = hit
        if kind == "err":
            raise value
        return value

    return wrapper


__all__ = ["memoize_parse", "parse_cache"]
