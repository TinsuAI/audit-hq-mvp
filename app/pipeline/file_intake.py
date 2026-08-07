"""Gợi ý loại tài liệu cho file cán bộ vừa thả vào ô thả của một kỳ (#88).

Hệ thống **gợi ý** loại và **nêu căn cứ**; cán bộ sửa trước khi nạp. Ba nguồn căn
cứ, mạnh→yếu: cán bộ tự chọn · đã mở file và khớp bố cục · chỉ khớp tên file.

**Từ ngữ.** "Nhận ra" CHỈ dùng cho file đã mở và khớp bố cục. Khớp tên là *gợi ý* —
tên do người gõ, và bản gộp tay của PILOT_006 mang tên hợp lệ trong khi cấu trúc
sai (mất 28,5 tỷ ở 2.076 ô công thức).

**Thứ tự phân giải, theo số đo.** Khớp tên trước vì tức thì. Tên không phân giải
được thì mới mở nội dung, và CHỈ dưới `CONTENT_PROBE_MAX_BYTES`: mở nội dung mất
0,14–0,20 giây với biểu quyết toán nhỏ nhưng 96,93 giây với file 71,3MB. Dò nội
dung cũng KHÔNG nhận ra BCCT trong mọi trường hợp — `content_slots` chỉ thử ba biểu
quyết toán — nên file lớn tên không phân giải được đi thẳng vào danh sách cán bộ tự
chọn thay vì bắt cán bộ chờ một phép dò không kết luận được.

File chưa phân giải nằm ở thư mục `CHUA_PHAN_LOAI` của kỳ và KHÔNG vào registry:
`data_files.slot` không nhận rỗng, và `sync_data_files` chỉ quét ba thư mục biểu nên
thư mục này vô hình với mọi đường khác cho tới lúc cán bộ chọn loại.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.models.data_file import SLOT_ORDER
from app.pipeline.discover import content_slots

#: Loại đã gán bằng gì. Lưu ở `data_files.slot_basis`.
BASIS_NAME = "name"
BASIS_CONTENT = "content"
BASIS_OFFICER = "officer"

BASIS_LABEL_VI: dict[str, str] = {
    BASIS_NAME: "gợi ý theo tên file, chưa mở file",
    BASIS_CONTENT: "đã mở file, khớp bố cục",
    BASIS_OFFICER: "cán bộ chọn",
}

#: Trên ngưỡng này thì KHÔNG mở file để dò loại — xem docstring module.
CONTENT_PROBE_MAX_BYTES = 10 * 1024 * 1024

#: Thư mục giữ file chưa phân giải được loại, nằm trong thư mục kỳ.
STAGING_SUBDIR = "CHUA_PHAN_LOAI"

_EXCEL_EXT = {".xls", ".xlsx"}

# Dấu hiệu trong TÊN file → loại. Thứ tự có nghĩa: dấu hiệu hẹp trước dấu hiệu rộng.
# `m15a` phải đứng trước `m15` (chuỗi con), và dấu hiệu định mức / tờ khai phải đứng
# trước `nvl`/`npl` vì bảng định mức và báo cáo tờ khai cũng nhắc tới nguyên liệu.
_NAME_MARKERS: tuple[tuple[str, str], ...] = (
    ("m15a", "m15a"),
    ("mau15a", "m15a"),
    ("bieu15a", "m15a"),
    ("phuluc15a", "m15a"),
    ("m15", "m15"),
    ("mau15", "m15"),
    ("bieu15", "m15"),
    ("phuluc15", "m15"),
    ("m16", "m16"),
    ("mau16", "m16"),
    ("bieu16", "m16"),
    ("bcdm", "m16"),
    ("dinhmuc", "m16"),
    ("bcct", "bcct"),
    ("hangchitiet", "bcct"),
    ("tokhai", "bcct"),
    ("nvl", "m15"),
    ("npl", "m15"),
    ("thanhpham", "m15a"),
)


@dataclass(frozen=True)
class Proposal:
    """Loại được gợi ý cho một file, kèm căn cứ. `slot=None` = cán bộ tự chọn."""

    slot: str | None
    basis: str | None

    @property
    def resolved(self) -> bool:
        return self.slot is not None

    @property
    def basis_label(self) -> str:
        return BASIS_LABEL_VI.get(self.basis or "", "")


@dataclass(frozen=True)
class PendingUpload:
    """File đã lưu nhưng chưa có loại — chờ cán bộ chọn, chưa vào registry."""

    name: str
    size_bytes: int
    rel_path: str


def _fold(text: str) -> str:
    """Bỏ dấu, hạ chữ thường, giữ lại chữ và số (bỏ mọi ký tự ngăn cách)."""
    s = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def slot_from_name(filename: str) -> str | None:
    """Loại suy được từ TÊN file, không mở file. None = tên không phân giải được."""
    stem = Path(filename).stem
    compact = _fold(stem)
    for marker, slot in _NAME_MARKERS:
        if marker in compact:
            return slot
    tokens = "_" + re.sub(r"[^a-z0-9]+", "_", _spaced(stem)).strip("_") + "_"
    if "_sp_" in tokens or "spgsql" in compact:
        return "m15a"
    return None


def _spaced(text: str) -> str:
    """Như `_fold` nhưng GIỮ ranh giới từ — cần cho dấu hiệu ngắn dễ trùng (`sp`)."""
    s = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in s if not unicodedata.combining(c))


def propose(
    path: Path, *, year: int | None = None, size_bytes: int | None = None
) -> Proposal:
    """Gợi ý loại cho một file đã nằm trên đĩa. Xem thứ tự phân giải ở docstring module."""
    slot = slot_from_name(path.name)
    if slot is not None:
        return Proposal(slot, BASIS_NAME)

    size = size_bytes
    if size is None:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
    if size > CONTENT_PROBE_MAX_BYTES:
        return Proposal(None, None)

    found = content_slots(path, year)
    for candidate in SLOT_ORDER:
        if candidate in found:
            return Proposal(candidate, BASIS_CONTENT)
    return Proposal(None, None)


def staging_dir(raw_root: Path, code: str, year: int) -> Path:
    return Path(raw_root) / code / str(year) / STAGING_SUBDIR


def pending_years(raw_root: Path, code: str) -> set[int]:
    """Kỳ nào đang có file chờ chọn loại.

    Màn dữ liệu dựng danh sách kỳ từ DB, mà file chờ chọn loại chưa có trong DB —
    thiếu bước này thì một kỳ chỉ có file chờ sẽ không có dòng nào để hiện nó ra.
    """
    company_dir = Path(raw_root) / code
    if not company_dir.is_dir():
        return set()
    return {
        int(d.name)
        for d in company_dir.iterdir()
        if d.is_dir() and d.name.isdigit() and (d / STAGING_SUBDIR).is_dir()
    }


def pending_uploads(raw_root: Path, code: str, year: int) -> tuple[PendingUpload, ...]:
    """File của kỳ đang chờ cán bộ chọn loại, sắp theo tên."""
    d = staging_dir(raw_root, code, year)
    if not d.is_dir():
        return ()
    out: list[PendingUpload] = []
    for p in sorted(d.iterdir(), key=lambda x: x.name):
        if not p.is_file() or p.suffix.lower() not in _EXCEL_EXT:
            continue
        out.append(PendingUpload(
            name=p.name,
            size_bytes=p.stat().st_size,
            rel_path=str(p.relative_to(Path(raw_root))),
        ))
    return tuple(out)
