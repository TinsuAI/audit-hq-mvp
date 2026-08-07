"""Một tên duy nhất cho mỗi loại tài liệu, trên mọi màn hình (#98).

Kiểm ở mức DỮ LIỆU — gọi thẳng hàm sinh câu và đọc bảng nhãn, không so chuỗi tiếng
Việt trong HTML. Bảng nhãn duy nhất là `SLOT_LABEL_VI` ở `app/models/data_file.py`.
"""

from __future__ import annotations

import app.checks.registry as registry
import app.checks.sources as sources
from app.checks.not_evaluable import REMEDY_NEED_FILE_THIS_PERIOD, TARGET_DOCUMENT, RemedyTarget
from app.checks.sources import SOURCES, missing_sources_reason
from app.models.data_file import SLOT_LABEL_VI, SLOT_ORDER, SLOT_SHORT_VI
from app.pipeline.data_screen import _short_label
from app.pipeline.readiness import (
    SLOT_NEEDS_BOOK,
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NOT_PARSED,
    SLOT_PARSE_ERROR,
    SlotStatus,
    _check_group_message,
    _file_blocker_message,
    _slot_label,
    _stale_blocker,
)
from app.pipeline.validate import SLOT_LABEL
from app.routes.companies import _EVIDENCE_TABLE_LABEL, _TABLE_CONFIG

YEAR = 2025


class TestSingleLabelTable:
    def test_checks_sources_no_longer_defines_its_own_table(self):
        """Bảng thứ hai đã xoá — không còn nguồn nhãn nào ngoài `SLOT_LABEL_VI`."""
        assert not hasattr(sources, "SOURCE_LABEL_VI")
        assert "SOURCE_LABEL_VI" not in sources.__all__

    def test_registry_no_longer_reexports_the_deleted_table(self):
        assert not hasattr(registry, "SOURCE_LABEL_VI")

    def test_sources_and_slots_are_the_same_four_document_types(self):
        assert set(SOURCES) == set(SLOT_ORDER) == set(SLOT_LABEL_VI)


class TestNeighbouringFunctionsAgree:
    """Bốn hàm sinh câu cho cùng một loại tài liệu phải in CÙNG một tên.

    Đây là lỗi đo được ở #98: `_file_blocker_message` và `_check_group_message` đứng
    cạnh nhau trong một dòng kỳ mà lấy tên từ hai bảng khác nhau.
    """

    def _statuses(self, slot: str) -> list[SlotStatus]:
        return [
            SlotStatus(slot=slot, state=state, has_rows=False, stale=False)
            for state in (
                SLOT_NOT_PARSED,
                SLOT_PARSE_ERROR,
                SLOT_NEEDS_COLUMN_REVIEW,
                SLOT_NEEDS_BOOK,
            )
        ]

    def test_every_message_names_the_document_type_the_same_way(self):
        for slot in SLOT_ORDER:
            expected = SLOT_LABEL_VI[slot]
            assert _slot_label(slot) == expected
            assert expected in missing_sources_reason((slot,))
            assert expected in _check_group_message(
                REMEDY_NEED_FILE_THIS_PERIOD, RemedyTarget(TARGET_DOCUMENT, slot), YEAR
            )
            for status in self._statuses(slot):
                assert expected in _file_blocker_message(status, YEAR), (slot, status.state)

    def test_stale_blocker_uses_the_short_form_from_the_table(self):
        for slot in SLOT_ORDER:
            status = SlotStatus(slot=slot, state=SLOT_NOT_PARSED, has_rows=True, stale=True)
            blocker = _stale_blocker((status,), YEAR)
            assert blocker is not None
            assert SLOT_SHORT_VI[slot] in blocker.message


class TestShortFormComesFromTheTable:
    """AC4 — dạng ngắn do bảng nhãn cung cấp, nơi dùng không tự cắt chuỗi nữa."""

    def test_short_table_covers_every_slot(self):
        assert set(SLOT_SHORT_VI) == set(SLOT_ORDER)

    def test_short_form_is_the_head_of_the_long_form(self):
        for slot in SLOT_ORDER:
            assert SLOT_LABEL_VI[slot].startswith(SLOT_SHORT_VI[slot])

    def test_data_screen_short_label_reads_the_table(self):
        for slot in SLOT_ORDER:
            assert _short_label(slot) == SLOT_SHORT_VI[slot]


class TestOtherScreenTablesMatch:
    """Các bảng nhãn còn lại trên màn cán bộ phải trả đúng tên chuẩn."""

    def test_upload_diagnosis_labels_match(self):
        for slot in SLOT_ORDER:
            assert SLOT_LABEL[slot] == SLOT_LABEL_VI[slot]

    def test_raw_data_tab_labels_match(self):
        for slot in SLOT_ORDER:
            assert _TABLE_CONFIG[slot]["label"] == SLOT_LABEL_VI[slot]

    def test_evidence_block_labels_match(self):
        by_table = {
            "nvl_balances": "m15",
            "sp_balances": "m15a",
            "norms": "m16",
            "declaration_lines": "bcct",
        }
        for table, slot in by_table.items():
            assert _EVIDENCE_TABLE_LABEL[table] == SLOT_LABEL_VI[slot]
