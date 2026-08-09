"""Class có trong HTML MÁY CHỦ THẬT SỰ trả về, so với danh sách class đã xoá (#127).

`tests/test_static_assets.py` đọc stylesheet và ghim những tên đã xoá. Nó không trả lời
được câu hỏi ngược lại: màn hình có còn phát ra một trong những tên đó không. Lượt quét
mã nguồn đã thử trả lời và trả lời SAI — tên `date` nằm trong dữ liệu Python
(`_TABLE_CONFIG`) rồi ra màn qua `<td class="{{ cls }}">`, không nằm trong template nào,
nên lượt quét báo "không ai dùng".

Ở đây gọi thẳng từng màn qua `TestClient` và đọc thuộc tính `class` của HTML trả về. Đầu
ra của máy chủ không có đường vòng nào: tên ghép lúc chạy, tên do Jinja dựng, tên nằm
trong dữ liệu Python đều đã thành chữ ở đây.

Giới hạn phải nói rõ: phép này KHÔNG chứng minh màn hình đúng kiểu. Nó chứng minh màn
hình không gọi tới một rule đã bị xoá. Phần "trông ra sao" cần trình duyệt và nằm ở vé
bằng chứng feature (#129).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from tests.conftest import AppDb
from tests.helpers import m15_xlsx_bytes, upload_and_ingest
from tests.test_static_assets import DELETED_CLASSES

_CODE = "DN_RC"
_YEAR = 2024

_CLASS_ATTR = re.compile(r"""class\s*=\s*(["'])(.*?)\1""", re.S)
_JINJA_LEFTOVER = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


@pytest.fixture
def client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=_CODE, name="Màn hình", tax_id="1"))
        db.commit()
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    upload_and_ingest(c, _CODE, "Mau15_NVL.xlsx", m15_xlsx_bytes())
    from tests.helpers import drain_jobs

    drain_jobs()
    return c


def _file_id(app_db: AppDb) -> int:
    with app_db.SessionLocal() as db:
        company = db.query(Company).filter_by(code=_CODE).one()
        return db.query(DataFile).filter_by(company_id=company.id).first().id


def _classes(html: str) -> set[str]:
    names: set[str] = set()
    for match in _CLASS_ATTR.finditer(html):
        for token in re.split(r"\s+", _JINJA_LEFTOVER.sub(" ", match.group(2))):
            if re.fullmatch(r"[-\w]+", token):
                names.add(token)
    return names


def _screens(app_db: AppDb) -> list[str]:
    """Luồng cán bộ VÀ màn quản trị — cả hai dùng chung một stylesheet."""
    fid = _file_id(app_db)
    return [
        "/companies",
        f"/companies/{_CODE}",
        f"/companies/{_CODE}/documents",
        f"/companies/{_CODE}/documents/file/{fid}",
        f"/companies/{_CODE}/data?year={_YEAR}&table=m15",
        "/jobs",
        "/catalog",
        "/admin",
        "/admin/users",
        "/admin/checks",
        "/admin/display",
        "/admin/risk-tiers",
        "/admin/audit",
        "/admin/ai",
    ]


def test_no_rendered_screen_asks_for_a_deleted_class(app_db: AppDb, client: TestClient):
    deleted = set(DELETED_CLASSES)
    offenders: dict[str, list[str]] = {}
    rendered = 0
    for url in _screens(app_db):
        response = client.get(url)
        if response.status_code != 200:
            continue
        rendered += 1
        hit = sorted(_classes(response.text) & deleted)
        if hit:
            offenders[url] = hit
    assert rendered >= 10, f"chỉ dựng được {rendered} màn — phép đo mất ý nghĩa"
    assert not offenders, f"màn còn gọi tới class đã xoá: {offenders}"
