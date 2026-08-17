"""Thư viện `app/` import thẳng thì phải khai thẳng trong `pyproject.toml`.

Ngày 2026-08-17 prod sập với `ModuleNotFoundError: No module named 'httpx'`. `httpx`
chưa bao giờ nằm trong `dependencies` — nó vào ảnh nhờ `openai` kéo theo. `openai` 3.1.0
chuyển sang `httpx2`, phụ thuộc bắc cầu biến mất, và `app/ai/config.py:17` gãy ngay ở
lượt import của `app.main`, tức container không khởi động được.

Bộ test KHÔNG bắt được: máy dev và runner CI cài cả `dev` extras, mà ở đó `httpx` có mặt
vì `TestClient` cần. Chỉ ảnh production mới thiếu. Vì vậy phép so ở đây đọc THẲNG
`pyproject.toml`, không hỏi môi trường đang chạy — hỏi môi trường là hỏi đúng chỗ đã che
mất lỗi.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app"

#: Tên phân phối (trên PyPI) → tên module khi import. Chỉ liệt kê chỗ hai tên KHÁC nhau.
DISTRIBUTION_TO_MODULE = {
    "python-multipart": "multipart",
    "python-dotenv": "dotenv",
    "pydantic-settings": "pydantic_settings",
    "uvicorn[standard]": "uvicorn",
}

#: Module không cần khai: thư viện chuẩn, và chính gói này.
ALLOWED_UNDECLARED = {"app"}


@lru_cache(maxsize=1)
def _declared_modules() -> frozenset[str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    modules = set()
    for spec in data["project"]["dependencies"]:
        name = re.split(r"[<>=!~;\s]", spec, maxsplit=1)[0]
        modules.add(DISTRIBUTION_TO_MODULE.get(name, name.replace("-", "_")))
    return frozenset(modules)


@lru_cache(maxsize=1)
def _imported_modules() -> frozenset[str]:
    """Module gốc mà mọi file dưới `app/` import, kể cả import trong hàm."""
    found: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return frozenset(found)


def test_every_third_party_import_in_app_is_a_declared_dependency() -> None:
    """Bắc cầu qua phụ thuộc của thư viện khác là dựa vào thứ mình không kiểm soát."""
    third_party = {
        name
        for name in _imported_modules()
        if name not in sys.stdlib_module_names and name not in ALLOWED_UNDECLARED
    }
    missing = sorted(third_party - _declared_modules())
    assert not missing, (
        "module `app/` import thẳng mà KHÔNG khai trong `pyproject.toml` "
        f"`[project.dependencies]`: {missing}. Chúng đang vào ảnh nhờ phụ thuộc bắc cầu "
        "của gói khác, và biến mất ngay khi gói đó đổi phụ thuộc."
    )


def test_httpx_is_declared_at_runtime_not_only_for_dev() -> None:
    """Ghim riêng ca đã làm sập prod ngày 2026-08-17."""
    assert "httpx" in _declared_modules()
