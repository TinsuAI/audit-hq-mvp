"""Tests cho UOM helpers + C3.3 severity ladder.

UOM canonical/aliases được seed trong conftest.session fixture.
"""

from __future__ import annotations

import pytest

from app.checks.uom import UomMatch, compare, get_family, resolve_canonical
from app.models import UomAlias
from scripts.seed_uom import _LEFT_UNRESOLVED_ON_PURPOSE


def _add_alias(session, alias: str, canonical: str):
    session.add(UomAlias(alias=alias, canonical_code=canonical))
    session.commit()
    from app.checks.uom import invalidate_cache
    invalidate_cache()


def test_resolve_canonical_basic(session):
    assert resolve_canonical(session, "MTR") == "MTR"
    assert resolve_canonical(session, "METRES") == "MTR"
    assert resolve_canonical(session, "m") == "MTR"
    _add_alias(session, "CHIẾC", "PCE")
    assert resolve_canonical(session, "CHIẾC") == "PCE"


def test_resolve_unknown_returns_none(session):
    assert resolve_canonical(session, "UNKNOWN_UNIT") is None
    assert resolve_canonical(session, None) is None
    assert resolve_canonical(session, "") is None


def test_get_family(session):
    assert get_family(session, "MTR") == "length"
    assert get_family(session, "CM") == "length"
    assert get_family(session, "KG") == "mass"
    assert get_family(session, "GAM") == "mass"
    assert get_family(session, "UNKNOWN") is None


def test_compare_equivalent_via_alias(session):
    # MTR ↔ METRES = same canonical → EQUIVALENT
    assert compare(session, "MTR", "METRES") == UomMatch.EQUIVALENT
    assert compare(session, "KG", "KGM") == UomMatch.EQUIVALENT
    _add_alias(session, "PCS", "PCE")
    _add_alias(session, "CHIẾC", "PCE")
    assert compare(session, "PCS", "CHIẾC") == UomMatch.EQUIVALENT


def test_compare_same_family_convertible(session):
    # MTR vs CMT: cùng family length nhưng khác canonical → SAME_FAMILY
    assert compare(session, "MTR", "CM") == UomMatch.SAME_FAMILY
    assert compare(session, "KG", "GAM") == UomMatch.SAME_FAMILY


def test_compare_different_family(session):
    # MTR (length) vs KG (mass) → DIFFERENT
    assert compare(session, "MTR", "KG") == UomMatch.DIFFERENT
    assert compare(session, "PCE", "MTR") == UomMatch.DIFFERENT


def test_compare_unknown_units(session):
    # Cả 2 unknown nhưng raw equal → EQUIVALENT (raw fallback)
    assert compare(session, "FOO", "FOO") == UomMatch.EQUIVALENT
    # 1 known, 1 unknown → UNRESOLVED: hệ thống KHÔNG BIẾT, chưa chứng minh lệch.
    assert compare(session, "MTR", "FOO") == UomMatch.UNRESOLVED


def test_compare_unresolved_is_not_different(session):
    """Không resolve được ≠ khác họ đơn vị (#115).

    Gộp hai ca này vào DIFFERENT là dán "đã chứng minh lệch" lên chỗ chưa đo được.
    """
    # Một vế không resolve.
    assert compare(session, "KG", "KHONG_CO_TRONG_BANG") == UomMatch.UNRESOLVED
    # Cả hai vế không resolve, chuỗi raw khác nhau.
    assert compare(session, "LẠ_MỘT", "LẠ_HAI") == UomMatch.UNRESOLVED
    # Vế nào cũng resolve được thì đường cũ giữ nguyên.
    assert compare(session, "MTR", "KG") == UomMatch.DIFFERENT
    assert compare(session, "MTR", "CM") == UomMatch.SAME_FAMILY


def test_compare_normalizes_case_and_whitespace(session):
    assert compare(session, "  mtr  ", "Metres") == UomMatch.EQUIVALENT


def test_resolve_compound_with_separator(session):
    # "Cái/Chiếc" — cả 2 phần đều map về PCE → resolve PCE.
    _add_alias(session, "CHIẾC", "PCE")
    _add_alias(session, "CÁI", "PCE")
    assert resolve_canonical(session, "Cái/Chiếc") == "PCE"
    assert resolve_canonical(session, "CHIẾC / CÁI") == "PCE"


def test_compare_with_compound_unit(session):
    _add_alias(session, "CHIẾC", "PCE")
    _add_alias(session, "CÁI", "PCE")
    # PCE vs "Cái/Chiếc" → EQUIVALENT
    assert compare(session, "PCE", "Cái/Chiếc") == UomMatch.EQUIVALENT


def test_resolve_compound_ambiguous_returns_none(session):
    # "KG, GAM" — 2 canonical khác nhau → ambiguous → None
    assert resolve_canonical(session, "KG, GAM") is None


def test_resolve_compound_lenient_with_unknown_parts(session):
    # "Cái/UNKNOWN_FOO" — 1 phần PCE, 1 unknown → resolve PCE (lenient).
    _add_alias(session, "CÁI", "PCE")
    assert resolve_canonical(session, "Cái/UNKNOWN_FOO") == "PCE"


# --- Bảng seed thật: chuỗi đơn vị đo được trong kho phải resolve (#115) ---


def _seed_full_uom(session):
    """Nạp trọn CANONICALS + ALIASES của `scripts.seed_uom` vào phiên test.

    Fixture `session` chỉ seed 5 canonical tối thiểu. Các test dưới đây khẳng định
    trên BẢNG SEED THẬT — đó mới là thứ chạy ở môi trường thật.
    """
    from app.checks.uom import invalidate_cache
    from app.models import UomCanonical
    from scripts.seed_uom import ALIASES, CANONICALS

    have_canon = {c for (c,) in session.query(UomCanonical.code).all()}
    session.add_all([
        UomCanonical(code=code, family=family, base_factor=factor, name_vi=name, description=desc)
        for code, family, factor, name, desc in CANONICALS
        if code not in have_canon
    ])
    session.flush()
    have_alias = {a for (a,) in session.query(UomAlias.alias).all()}
    session.add_all([
        UomAlias(alias=alias, canonical_code=code)
        for alias, code in ALIASES
        if alias not in have_alias
    ])
    session.commit()
    invalidate_cache()


# Chuỗi đo được trong kho 08/08 (7 DN, 270.385 dòng định mức) → canonical mong đợi.
# Số dòng ghi kèm để biết chuỗi nào đáng giá.
_MEASURED_RESOLVABLE = [
    ("Lon/Can", "CAN", 1720),
    ("Lon/can", "CAN", 14),
    ("Phút vuông", "FTK", 539),
    ("Gói", "PKG", 54),
    ("Cuốn", "ROL", 40),
    ("YRD", "YDK", 18),
    ("ONG", "BTL", 17),
    ("Ống", "BTL", 12),
    ("Quyển/Tập", "VOL", 8),
    ("Thanh/Mảnh/Miếng", "BAR", 7),
    ("RAM", "RIM", 6),
    ("Sợi", "STR", 6),
    ("SOI", "STR", 2),
    ("Quả", "PCE", 4),
    ("Tấn (hàm lượng KL)", "TNE", 2),
    ("Cây", "PCE", 1),
    ("Vỉ", "PKG", 1),
]


@pytest.mark.parametrize(("raw", "canonical", "_rows"), _MEASURED_RESOLVABLE)
def test_measured_unit_strings_resolve(session, raw, canonical, _rows):
    """Đi qua đúng đường `resolve_canonical` — không tra thẳng bảng alias."""
    _seed_full_uom(session)
    assert resolve_canonical(session, raw) == canonical


# Chuỗi CỐ Ý để không resolve: không phải đơn vị, hoặc không tra được nguồn.
# Chúng là lý do tồn tại của UNRESOLVED — gán bừa một canonical là bịa ra hiểu biết.
_MEASURED_LEFT_UNRESOLVED = _LEFT_UNRESOLVED_ON_PURPOSE


@pytest.mark.parametrize("raw", _MEASURED_LEFT_UNRESOLVED)
def test_placeholder_and_garbage_units_stay_unresolved(session, raw):
    _seed_full_uom(session)
    assert resolve_canonical(session, raw) is None


def test_compound_with_several_known_parts_still_compares_by_family(session):
    """Chuỗi ghép nhập nhằng canonical nhưng RÕ họ thì vẫn kết luận được (#115).

    `Kiện/Hộp/Bao/Gói` trước đây resolve ra BOX chỉ vì `HỘP` tình cờ là phần DUY NHẤT
    có trong bảng. Thêm bí danh `GÓI`→PKG làm chuỗi thành nhập nhằng hai canonical,
    và nếu chỉ dựa vào canonical thì một phát hiện lệch thật (đóng gói vs khối lượng)
    bị hạ xuống "chưa tra được". Đo trên kho: đúng 2 phát hiện của DN 8 kỳ 2024/2025.
    """
    _seed_full_uom(session)
    # Không chốt được MỘT canonical — đó là sự thật, giữ nguyên.
    assert resolve_canonical(session, "Kiện/Hộp/Bao/Gói") is None
    # Nhưng mọi phần tra được đều thuộc họ đóng gói, nên so với khối lượng vẫn là lệch.
    assert compare(session, "Kilogam", "Kiện/Hộp/Bao/Gói") == UomMatch.DIFFERENT
    # Hai chuỗi cùng họ mà không chốt được canonical → cùng họ, không phải lệch.
    assert compare(session, "Hộp/Gói", "Gói/Hộp") == UomMatch.EQUIVALENT
    assert compare(session, "Kiện/Hộp/Bao/Gói", "Thùng") == UomMatch.SAME_FAMILY
    # Còn thật sự không tra được phần nào thì vẫn là chưa biết.
    assert compare(session, "Kilogam", "UNL") == UomMatch.UNRESOLVED


def test_new_aliases_do_not_merge_across_families(session):
    """Alias mới không được kéo hai đơn vị khác họ về cùng canonical."""
    _seed_full_uom(session)
    # 'Lon/Can' là đơn vị ĐẾM — không được rơi vào mass/length.
    assert get_family(session, "Lon/Can") == "count"
    assert get_family(session, "Lon/Can") not in {"mass", "length", "area", "volume"}
    # 'Phút vuông' là đơn vị DIỆN TÍCH da giày (đối chiếu thẳng với FTK trong kho).
    assert get_family(session, "Phút vuông") == "area"
    # Yard là độ dài, không phải đếm.
    assert get_family(session, "YRD") == "length"
    # Không alias mới nào trỏ tới canonical không tồn tại.
    from scripts.seed_uom import ALIASES, CANONICALS
    codes = {c for c, *_ in CANONICALS}
    assert {code for _, code in ALIASES} <= codes


def test_alias_table_has_no_duplicate_entries():
    """Alias trùng thì `seed_aliases` bỏ qua im lặng — bảng nguồn phải sạch."""
    from scripts.seed_uom import ALIASES
    seen = [a for a, _ in ALIASES]
    dupes = {a for a in seen if seen.count(a) > 1}
    assert not dupes, f"alias khai trùng: {sorted(dupes)}"


# --- C3.3 với UOM severity ladder ---


def test_c3_3_severity_ladder_with_uom(session, company):
    from app.checks.c3_classify import check_c3_3
    from tests.conftest import add_decl, add_nvl

    # NVL A: KG vs GAM (same family, different canonical) → INFO
    add_nvl(session, company.id, material_code="A", unit="KG")
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, unit="GAM")

    # NVL B: KG vs PCE (different family) → CRITICAL
    add_nvl(session, company.id, material_code="B", unit="KG")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="B", quantity=10, unit="PCE")

    # NVL C: MTR vs METRES (equivalent via alias) → SKIP
    add_nvl(session, company.id, material_code="C", unit="MTR")
    add_decl(session, company.id, declaration_no="3", customs_code="E31",
             item_code="C", quantity=10, unit="METRES")

    session.commit()
    findings = check_c3_3(session, company.id, 2024)

    by_code = {f.subject_key: f for f in findings}
    assert "C" not in by_code
    assert by_code["A"].severity == "info"
    assert by_code["A"].details["uom_match"] == "same_family"
    assert by_code["B"].severity == "critical"
    assert by_code["B"].details["uom_match"] == "different"


def test_c3_3_unresolvable_unit_is_not_critical(session, company):
    """Đơn vị không tra được → "chưa biết", KHÔNG phải Nghiêm trọng (#115).

    Đây là ca `Lon/Can` vs `Cái/Chiếc` của kho thật trước khi có alias: hệ thống
    không biết `Lon/Can` là gì, mà vẫn kết luận lệch ở mức nặng nhất.
    """
    from app.checks.c3_classify import check_c3_3
    from tests.conftest import add_decl, add_nvl

    # NVL D: PCE vs chuỗi không có trong bảng → UNRESOLVED.
    add_nvl(session, company.id, material_code="D", unit="PCE")
    add_decl(session, company.id, declaration_no="4", customs_code="E31",
             item_code="D", quantity=10, unit="ĐƠN_VỊ_LẠ")
    # NVL E: KG vs PCE — lệch thật, phải GIỮ Nghiêm trọng (cổng chống sửa quá tay).
    add_nvl(session, company.id, material_code="E", unit="KG")
    add_decl(session, company.id, declaration_no="5", customs_code="E31",
             item_code="E", quantity=10, unit="PCE")

    session.commit()
    by_code = {f.subject_key: f for f in check_c3_3(session, company.id, 2024)}

    assert by_code["D"].details["uom_match"] == "unresolved"
    assert by_code["D"].severity == "warning"
    assert "ĐƠN_VỊ_LẠ" in by_code["D"].title
    # Lệch thật không bị hạ mức theo.
    assert by_code["E"].severity == "critical"
    assert by_code["E"].details["uom_match"] == "different"


def test_c3_3_real_mismatch_wins_over_unresolvable(session, company):
    """Một mã vừa có đơn vị lệch thật vừa có đơn vị không tra được → vẫn Nghiêm trọng.

    Nếu UNRESOLVED che mất DIFFERENT thì thêm một chuỗi rác vào file là hạ được
    mức của một phát hiện thật.
    """
    from app.checks.c3_classify import check_c3_3
    from tests.conftest import add_decl, add_nvl

    add_nvl(session, company.id, material_code="F", unit="KG")
    add_decl(session, company.id, declaration_no="6", customs_code="E31",
             item_code="F", quantity=10, unit="PCE")
    add_decl(session, company.id, declaration_no="7", customs_code="E31",
             item_code="F", quantity=10, unit="ĐƠN_VỊ_LẠ")

    session.commit()
    by_code = {f.subject_key: f for f in check_c3_3(session, company.id, 2024)}
    assert by_code["F"].severity == "critical"
    assert by_code["F"].details["uom_match"] == "different"


def test_unresolvable_predicate_is_the_one_compare_uses(session):
    """`is_unresolvable` phải khớp ĐÚNG vị ngữ `compare()` dùng để trả UNRESOLVED.

    Ca bắt lỗi: chuỗi ghép nhập nhằng canonical (`Kiện/Hộp/Bao/Gói` → BOX lẫn PKG) có
    `resolve_canonical() is None` nhưng VẪN tra được họ. Lấy `resolve_canonical() is
    None` làm vị ngữ thì C3.3 nêu tên nó trong câu "không có trong bảng đơn vị chuẩn"
    — sai, vì nó CÓ trong bảng.
    """
    from app.checks.uom import is_unresolvable

    _seed_full_uom(session)
    ambiguous = "Kiện/Hộp/Bao/Gói"
    assert resolve_canonical(session, ambiguous) is None
    assert is_unresolvable(session, ambiguous) is False

    for raw in _MEASURED_LEFT_UNRESOLVED:
        assert is_unresolvable(session, raw) is True, raw

    # Và vị ngữ khớp hành vi thật của compare(): nhập nhằng canonical mà rõ họ thì
    # KHÔNG ra UNRESOLVED, còn chuỗi không tra được phần nào thì có.
    assert compare(session, ambiguous, "KG") == UomMatch.DIFFERENT
    assert compare(session, "UNL", "KG") == UomMatch.UNRESOLVED
