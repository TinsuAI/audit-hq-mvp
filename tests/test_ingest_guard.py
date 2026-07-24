"""Guard: pháp nhân nhiều sổ (book) không re-ingest qua đường bare ingest (ADR #19).

`ingest()` xoá sạch Tier-1 của (company, year) rồi nạp từ MỘT thư mục — với pháp nhân
nhiều sổ sẽ huỷ mất các sổ khác. Guard chặn trước khi xoá.
"""

from __future__ import annotations

import pytest

from app.pipeline.ingest import _guard_single_book
from tests.conftest import add_nvl


def test_ingest_guard_blocks_multibook(session, company):
    add_nvl(session, company.id, material_code="X", imported=10, book="EPE")
    add_nvl(session, company.id, material_code="Y", imported=10, book="GC")
    session.commit()
    with pytest.raises(ValueError):
        _guard_single_book(session, company.id, 2024, company.code)


def test_ingest_guard_allows_single_book(session, company):
    add_nvl(session, company.id, material_code="X", imported=10)  # book=None
    session.commit()
    _guard_single_book(session, company.id, 2024, company.code)  # không raise
