"""Seed bảng UOM canonical + aliases.

Idempotent: skip nếu code/alias đã có. Chạy 1 lần sau migration, hoặc khi
thêm canonical/alias mới trong code (commit thêm tuple vào CANONICALS hoặc
ALIASES, chạy lại script).

Usage:
    python -m scripts.seed_uom
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import UomAlias, UomCanonical

# (code, family, base_factor, name_vi, description)
# Family: length, mass, area, volume, count, count_packaging, time, energy
# base_factor: nhân vào để ra đơn vị gốc family (vd 1m=1.0, 1cm=0.01, 1km=1000)
CANONICALS: list[tuple[str, str, float, str, str]] = [
    # Length
    ("MTR", "length", 1.0,    "Mét",         "Đơn vị độ dài chuẩn UN/CEFACT"),
    ("CMT", "length", 0.01,   "Cen-ti-mét",  "1 cm = 0.01 m"),
    ("MMT", "length", 0.001,  "Mi-li-mét",   "1 mm = 0.001 m"),
    ("KMT", "length", 1000.0, "Ki-lô-mét",   "1 km = 1000 m"),
    ("INH", "length", 0.0254, "Inch",        "1 inch = 0.0254 m"),
    # Mass
    ("KGM", "mass",   1.0,    "Ki-lô-gam",   "Đơn vị khối lượng chuẩn"),
    ("GRM", "mass",   0.001,  "Gam",         "1 g = 0.001 kg"),
    ("TNE", "mass",   1000.0, "Tấn (metric)","1 ton = 1000 kg"),
    ("MGM", "mass",   1e-6,   "Mi-li-gam",   "1 mg = 0.000001 kg"),
    ("LBR", "mass",   0.4536, "Pound",       "1 lb = 0.4536 kg"),
    # Area
    ("MTK", "area",   1.0,    "Mét vuông",   "Đơn vị diện tích chuẩn"),
    ("CMK", "area",   0.0001, "Cen-ti-mét²", "1 cm² = 0.0001 m²"),
    ("FTK", "area",   0.0929, "Foot²",       "Mét vuông da, đơn vị da giày"),
    # Volume
    ("MTQ", "volume", 1.0,    "Mét khối",    "Đơn vị thể tích chuẩn"),
    ("LTR", "volume", 0.001,  "Lít",         "1 L = 0.001 m³"),
    ("MLT", "volume", 1e-6,   "Mi-li-lít",   "1 ml = 0.000001 m³"),
    # Count
    ("PCE", "count",  1.0,    "Chiếc / cái", "Đơn vị đếm cá thể"),
    ("PR",  "count",  2.0,    "Đôi / cặp",   "1 pair = 2 cái"),
    ("DZN", "count",  12.0,   "Tá",          "1 dozen = 12 cái"),
    # Sheet/board (đếm theo dạng phẳng)
    ("TOO", "count_packaging", 1.0, "Tờ",     "Tờ giấy / vải / film"),
    ("TAM", "count_packaging", 1.0, "Tấm",    "Tấm board / kim loại / nhựa"),
    # Packaging
    ("ROL", "count_packaging", 1.0, "Cuộn",   "Cuộn cuốn (chỉ, vải, giấy)"),
    ("SET", "count_packaging", 1.0, "Bộ",     "Bộ / set"),
    ("BOX", "count_packaging", 1.0, "Hộp",    "Hộp / box"),
    ("BAG", "count_packaging", 1.0, "Túi",    "Túi / bag"),
    ("BTL", "count_packaging", 1.0, "Chai / lọ / tuýp", "Chai / bottle / jar / tube"),
    ("CTN", "count_packaging", 1.0, "Thùng / carton", "Thùng carton"),
    # --- #115: chuỗi đơn vị đo được trong kho mà bảng chưa có ---
    # Họ đơn vị chọn theo ĐƠN VỊ ĐỐI CHIẾU THẬT trong kho, không theo cảm nhận về
    # từ: đặt sai họ thì phát hiện đang là "chưa tra được" bị đẩy thành "khác họ"
    # = Nghiêm trọng, tức là sửa alias lại đẻ ra phát hiện nặng mới.
    # `Lon/Can` (1.720 dòng) chỉ từng đối chiếu với `Cái/Chiếc` (PCE, họ count) →
    # để họ count thì ra Cùng họ (Thông tin), không phải Khác họ (Nghiêm trọng).
    ("CAN", "count", 1.0, "Lon / can", "Lon, can — đếm theo vỏ chứa"),
    ("VOL", "count", 1.0, "Quyển / tập", "Ấn phẩm đóng tập"),
    ("BAR", "count", 1.0, "Thanh / mảnh / miếng", "Đếm theo thanh, mảnh, miếng rời"),
    ("STR", "count", 1.0, "Sợi", "Sợi chỉ, sợi dây"),
    ("PKG", "count_packaging", 1.0, "Gói / vỉ", "Gói, packet, vỉ"),
    ("RIM", "count_packaging", 1.0, "Ram giấy", "1 ram = 500 tờ"),
    ("YDK", "length", 0.9144, "Yard", "1 yard = 0.9144 m"),
]


# (alias_text_uppercase, canonical_code)
ALIASES: list[tuple[str, str]] = [
    # Length
    ("MTR", "MTR"), ("METRE", "MTR"), ("METRES", "MTR"), ("METER", "MTR"), ("METERS", "MTR"),
    ("M", "MTR"), ("MÉT", "MTR"), ("MET", "MTR"),
    ("CM", "CMT"), ("CMT", "CMT"), ("CENTIMETRE", "CMT"), ("CENTIMETER", "CMT"),
    ("CENTIMETRES", "CMT"), ("CENTIMETERS", "CMT"),
    ("MM", "MMT"), ("MMT", "MMT"), ("MILLIMETRE", "MMT"), ("MILLIMETER", "MMT"),
    ("KM", "KMT"), ("KMT", "KMT"), ("KILOMETRE", "KMT"), ("KILOMETER", "KMT"),
    ("INCH", "INH"), ("INH", "INH"), ('"', "INH"),
    # Mass
    ("KG", "KGM"), ("KGM", "KGM"), ("KILOGRAM", "KGM"), ("KILOGRAMS", "KGM"),
    ("KILOGAM", "KGM"), ("KÍLÔGAM", "KGM"),
    ("KILO-GRAMME", "KGM"), ("KILO-GRAMMES", "KGM"), ("KILOGRAMME", "KGM"), ("KILOGRAMMES", "KGM"),
    ("G", "GRM"), ("GR", "GRM"), ("GRM", "GRM"), ("GAM", "GRM"), ("GRAM", "GRM"), ("GRAMS", "GRM"),
    ("T", "TNE"), ("TN", "TNE"), ("TNE", "TNE"), ("TON", "TNE"), ("TONS", "TNE"), ("TẤN", "TNE"),
    ("MG", "MGM"), ("MGM", "MGM"), ("MILLIGRAM", "MGM"),
    ("LB", "LBR"), ("LBR", "LBR"), ("POUND", "LBR"), ("POUNDS", "LBR"),
    # Area
    ("M2", "MTK"), ("MTK", "MTK"), ("SQM", "MTK"), ("SQUARE METRE", "MTK"),
    ("SQUARE METRES", "MTK"), ("SQUARE METER", "MTK"), ("SQUARE METERS", "MTK"),
    ("MÉT VUÔNG", "MTK"), ("M VUÔNG", "MTK"),
    ("CM2", "CMK"), ("CMK", "CMK"), ("SQUARE CENTIMETRE", "CMK"),
    ("FTK", "FTK"), ("FT2", "FTK"), ("SQ FT", "FTK"), ("SQFT", "FTK"),
    # Volume
    ("M3", "MTQ"), ("MTQ", "MTQ"), ("CUBIC METRE", "MTQ"), ("CUBIC METRES", "MTQ"),
    ("L", "LTR"), ("LIT", "LTR"), ("LTR", "LTR"), ("LITRE", "LTR"), ("LITRES", "LTR"),
    ("LITER", "LTR"), ("LITERS", "LTR"), ("LÍT", "LTR"),
    ("ML", "MLT"), ("MLT", "MLT"), ("MILLILITRE", "MLT"), ("MILLILITER", "MLT"),
    # Count
    ("PCE", "PCE"), ("PCS", "PCE"), ("PC", "PCE"), ("PIECE", "PCE"), ("PIECES", "PCE"),
    ("CAI", "PCE"), ("CÁI", "PCE"), ("CHIEC", "PCE"), ("CHIẾC", "PCE"),
    ("UNIT", "PCE"), ("UNITS", "PCE"), ("UN", "PCE"), ("UNA", "PCE"), ("U", "PCE"),
    ("PR", "PR"), ("PAIR", "PR"), ("PAIRS", "PR"), ("DOI", "PR"), ("ĐÔI", "PR"),
    ("CAP", "PR"), ("CẶP", "PR"),
    ("DZN", "DZN"), ("DZ", "DZN"), ("DOZEN", "DZN"), ("TÁ", "DZN"),
    # Packaging
    ("ROL", "ROL"), ("ROLL", "ROL"), ("ROLLS", "ROL"), ("CUON", "ROL"), ("CUỘN", "ROL"),
    ("SET", "SET"), ("SETS", "SET"), ("BO", "SET"), ("BỘ", "SET"),
    ("TOO", "TOO"), ("TO", "TOO"), ("TỜ", "TOO"), ("SHEET", "TOO"), ("SHEETS", "TOO"),
    ("TAM", "TAM"), ("TẤM", "TAM"), ("BOARD", "TAM"), ("PANEL", "TAM"), ("PANELS", "TAM"),
    ("BOX", "BOX"), ("BOXES", "BOX"), ("HOP", "BOX"), ("HỘP", "BOX"),
    ("BAG", "BAG"), ("BAGS", "BAG"), ("TUI", "BAG"), ("TÚI", "BAG"),
    ("BTL", "BTL"), ("BOTTLE", "BTL"), ("BOTTLES", "BTL"), ("CHAI", "BTL"),
    ("LO", "BTL"), ("LỌ", "BTL"), ("JAR", "BTL"), ("TUYP", "BTL"), ("TUÝP", "BTL"), ("TUBE", "BTL"),
    ("CTN", "CTN"), ("CARTON", "CTN"), ("CARTONS", "CTN"), ("THUNG", "CTN"), ("THÙNG", "CTN"),
    # --- #115: bí danh cho chuỗi đơn vị đo được trong kho (08/08, 7 DN) ---
    # Khai từng PHẦN của chuỗi ghép, không khai cả chuỗi: `resolve_canonical` tách
    # theo [/,;|] rồi tra từng phần, nên `LON` + `CAN` phủ cả "Lon/Can" lẫn "Can/Lon".
    ("LON", "CAN"), ("CAN", "CAN"), ("TIN", "CAN"),
    ("QUYỂN", "VOL"), ("QUYEN", "VOL"), ("TẬP", "VOL"), ("TAP", "VOL"),
    ("THANH", "BAR"), ("MẢNH", "BAR"), ("MANH", "BAR"), ("MIẾNG", "BAR"), ("MIENG", "BAR"),
    ("SỢI", "STR"), ("SOI", "STR"),
    ("GÓI", "PKG"), ("GOI", "PKG"), ("PACK", "PKG"), ("PACKET", "PKG"),
    # Chỉ bản có dấu: "VI" trần hai chữ cái dễ đụng chuỗi khác, mà kho chỉ có "Vỉ".
    ("VỈ", "PKG"),
    ("RAM", "RIM"), ("REAM", "RIM"), ("RIM", "RIM"),
    ("YRD", "YDK"), ("YARD", "YDK"), ("YARDS", "YDK"), ("YD", "YDK"),
    # `Ống`/`ONG` = tuýp — BTL đã gom chai/lọ/tuýp/tube.
    ("ỐNG", "BTL"), ("ONG", "BTL"),
    # `Quả`, `Cây` là danh từ đếm cá thể — cùng canonical với cái/chiếc.
    ("QUẢ", "PCE"), ("QUA", "PCE"), ("CÂY", "PCE"), ("CAY", "PCE"),
    # `Cuốn` (dấu sắc) trong kho được dùng LẪN với `CUON` (=cuộn) trên cùng mã NVL —
    # đo được ở 3 phát hiện C3.3. Theo dữ liệu, không theo nghĩa từ điển của "cuốn".
    ("CUỐN", "ROL"),
    # `Phút vuông` chỉ từng đối chiếu thẳng với FTK, và FTK vốn khai là đơn vị da giày.
    ("PHÚT VUÔNG", "FTK"), ("PHUT VUONG", "FTK"),
    # Tấn có chú thích hàm lượng kim loại vẫn là tấn.
    ("TẤN (HÀM LƯỢNG KL)", "TNE"),
]

# Chuỗi ĐO ĐƯỢC nhưng CỐ Ý không khai bí danh — chúng đi vào nhánh UNRESOLVED (#115).
# Gán bừa một canonical ở đây là bịa ra hiểu biết hệ thống không có:
#   UNL (277 dòng) · UNK (12)      — chỗ giữ chỗ "không rõ", đúng nghĩa là chưa biết
#   I/át (23) · I/at (9)           — chỉ từng đối chiếu với YRD, chưa tra được nguồn
#   1000 viên (2)                  — mã hoá cả lượng lẫn đơn vị, không phải đơn vị đơn
#   Real Brasil (1) · Panh (1)     — giá trị rác, #115 ghi rõ để ngoài phạm vi
_LEFT_UNRESOLVED_ON_PURPOSE = (
    "UNL", "UNK", "I/át", "I/at", "1000 viên", "Real Brasil", "Panh",
)


def seed_canonicals(session) -> int:
    existing = set(session.scalars(select(UomCanonical.code)).all())
    added = 0
    for code, family, factor, name_vi, desc in CANONICALS:
        if code in existing:
            continue
        session.add(UomCanonical(
            code=code, family=family, base_factor=factor,
            name_vi=name_vi, description=desc,
        ))
        added += 1
    session.commit()
    return added


def seed_aliases(session) -> int:
    existing_aliases = {a.upper() for a in session.scalars(select(UomAlias.alias)).all()}
    canonical_codes = set(session.scalars(select(UomCanonical.code)).all())
    added = 0
    for alias, code in ALIASES:
        alias_up = alias.upper()
        if alias_up in existing_aliases:
            continue
        if code not in canonical_codes:
            print(f"  ⚠ Skip alias {alias!r} → unknown canonical {code!r}", file=sys.stderr)
            continue
        session.add(UomAlias(alias=alias_up, canonical_code=code))
        added += 1
    session.commit()
    return added


def main() -> int:
    with SessionLocal() as session:
        n_can = seed_canonicals(session)
        n_alias = seed_aliases(session)
    print(f"✓ Seeded {n_can} canonical + {n_alias} alias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
