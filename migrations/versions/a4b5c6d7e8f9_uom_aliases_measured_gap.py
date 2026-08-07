"""uom: bổ sung canonical + bí danh cho chuỗi đơn vị đo được trong kho (#115)

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-08 03:10:00.000000

Đo 08/08 trên 7 DN / 270.385 dòng định mức: 24 trong 72 chuỗi đơn vị có thật không
tra được canonical nào. `compare()` gộp "không tra được" vào DIFFERENT nên chúng ra
Nghiêm trọng như thể đã chứng minh lệch.

Dữ liệu khai THẲNG trong revision này, không import từ `scripts.seed_uom`: sửa danh
sách seed về sau không được đổi ngược nội dung của một revision đã chạy.

Bảy chuỗi CỐ Ý không khai ở đây (UNL · UNK · I/át · I/at · 1000 viên · Real Brasil ·
Panh) — xem `_LEFT_UNRESOLVED_ON_PURPOSE` ở `scripts/seed_uom.py`.

Idempotent hai chiều: upgrade bỏ qua khoá đã có, downgrade chỉ xoá đúng khoá mình
thêm. Chạy được trên DB đã seed tay qua `/admin/units`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a4b5c6d7e8f9'
down_revision: str | Sequence[str] | None = 'f3a4b5c6d7e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (code, family, base_factor, name_vi, description)
_CANONICALS: list[tuple[str, str, float, str, str]] = [
    ("CAN", "count", 1.0, "Lon / can", "Lon, can — đếm theo vỏ chứa"),
    ("VOL", "count", 1.0, "Quyển / tập", "Ấn phẩm đóng tập"),
    ("BAR", "count", 1.0, "Thanh / mảnh / miếng", "Đếm theo thanh, mảnh, miếng rời"),
    ("STR", "count", 1.0, "Sợi", "Sợi chỉ, sợi dây"),
    ("PKG", "count_packaging", 1.0, "Gói / vỉ", "Gói, packet, vỉ"),
    ("RIM", "count_packaging", 1.0, "Ram giấy", "1 ram = 500 tờ"),
    ("YDK", "length", 0.9144, "Yard", "1 yard = 0.9144 m"),
]

# (alias viết HOA, canonical_code)
_ALIASES: list[tuple[str, str]] = [
    ("LON", "CAN"), ("CAN", "CAN"), ("TIN", "CAN"),
    ("QUYỂN", "VOL"), ("QUYEN", "VOL"), ("TẬP", "VOL"), ("TAP", "VOL"),
    ("THANH", "BAR"), ("MẢNH", "BAR"), ("MANH", "BAR"), ("MIẾNG", "BAR"), ("MIENG", "BAR"),
    ("SỢI", "STR"), ("SOI", "STR"),
    ("GÓI", "PKG"), ("GOI", "PKG"), ("PACK", "PKG"), ("PACKET", "PKG"),
    ("VỈ", "PKG"),
    ("RAM", "RIM"), ("REAM", "RIM"), ("RIM", "RIM"),
    ("YRD", "YDK"), ("YARD", "YDK"), ("YARDS", "YDK"), ("YD", "YDK"),
    ("ỐNG", "BTL"), ("ONG", "BTL"),
    ("QUẢ", "PCE"), ("QUA", "PCE"), ("CÂY", "PCE"), ("CAY", "PCE"),
    ("CUỐN", "ROL"),
    ("PHÚT VUÔNG", "FTK"), ("PHUT VUONG", "FTK"),
    ("TẤN (HÀM LƯỢNG KL)", "TNE"),
]


def upgrade() -> None:
    conn = op.get_bind()

    have_canon = {
        row[0] for row in conn.execute(sa.text("SELECT code FROM uom_canonical")).all()
    }
    for code, family, factor, name_vi, desc in _CANONICALS:
        if code in have_canon:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO uom_canonical (code, family, base_factor, name_vi, description) "
                "VALUES (:code, :family, :factor, :name_vi, :desc)"
            ),
            {"code": code, "family": family, "factor": factor, "name_vi": name_vi, "desc": desc},
        )

    # Bí danh trỏ tới canonical đã có từ trước (BTL, PCE, ROL, FTK, TNE) chỉ thêm được
    # khi canonical đó thật sự tồn tại — DB chưa seed thì bỏ qua, không nổ FK.
    codes_now = {
        row[0] for row in conn.execute(sa.text("SELECT code FROM uom_canonical")).all()
    }
    have_alias = {
        row[0] for row in conn.execute(sa.text("SELECT alias FROM uom_aliases")).all()
    }
    for alias, code in _ALIASES:
        if alias in have_alias or code not in codes_now:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO uom_aliases (alias, canonical_code) VALUES (:alias, :code)"
            ),
            {"alias": alias, "code": code},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for alias, _code in _ALIASES:
        conn.execute(
            sa.text("DELETE FROM uom_aliases WHERE alias = :alias"), {"alias": alias}
        )
    for code, *_rest in _CANONICALS:
        conn.execute(
            sa.text("DELETE FROM uom_canonical WHERE code = :code"), {"code": code}
        )
