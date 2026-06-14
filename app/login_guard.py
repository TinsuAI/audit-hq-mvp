"""Chống dò mật khẩu — khoá đăng nhập tạm theo IP sau nhiều lần sai.

In-memory (1 process uvicorn cho pilot). Restart sẽ reset — chấp nhận được; mục
tiêu chỉ là làm chậm brute-force, không phải kho bền vững. Khoá theo IP để 1 IP
thử nhiều username vẫn bị tính chung.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

WINDOW_S = 300       # cửa sổ trượt đếm lần sai
MAX_FAILS = 8        # số lần sai trong cửa sổ → khoá
LOCKOUT_S = 300      # thời gian khoá

_fails: dict[str, deque[float]] = defaultdict(deque)
_locked_until: dict[str, float] = {}


def locked_seconds(key: str) -> int:
    """Số giây còn bị khoá cho `key`. 0 nếu không bị khoá."""
    until = _locked_until.get(key)
    if until is None:
        return 0
    remaining = until - time.monotonic()
    if remaining <= 0:
        _locked_until.pop(key, None)
        return 0
    return int(remaining) + 1


def record_failure(key: str) -> None:
    """Ghi 1 lần đăng nhập sai; khoá `key` nếu vượt ngưỡng trong cửa sổ."""
    now = time.monotonic()
    dq = _fails[key]
    dq.append(now)
    while dq and now - dq[0] > WINDOW_S:
        dq.popleft()
    if len(dq) >= MAX_FAILS:
        _locked_until[key] = now + LOCKOUT_S
        dq.clear()


def clear(key: str) -> None:
    """Reset bộ đếm + khoá cho `key` (gọi sau khi đăng nhập thành công)."""
    _fails.pop(key, None)
    _locked_until.pop(key, None)


def reset_all() -> None:
    """Xoá toàn bộ trạng thái (dùng cho test)."""
    _fails.clear()
    _locked_until.clear()
