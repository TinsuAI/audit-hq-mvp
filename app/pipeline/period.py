"""Suy cửa sổ kỳ báo cáo (period_from, period_to) cho một (company, period_year).

Ưu tiên: bản `is_manual` cán bộ đã lưu > tiêu đề file (đủ cả 2 ngày) > niên độ mặc
định của DN (`companies.fiscal_start_month`) > dương lịch. Upsert vào
`company_periods` nhưng KHÔNG ghi đè bản `is_manual=True`.

Nhãn năm = năm BẮT ĐẦU kỳ (ADR #23 T2). Pháp luật định danh kỳ CHỈ bằng khoảng ngày
("Từ ngày… đến ngày…"), không có quy ước tên "năm tài chính 20XX" — nên nhãn là khoá
nội bộ, và mọi màn hiện nhãn kỳ ≠ dương lịch phải in kèm khoảng ngày.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy import select

from app.adapters._common import CompanyHeader
from app.models import Company, CompanyPeriod

# Bốn mốc điểm a khoản 1 Điều 12 Luật Kế toán 88/2015 cho phép cho niên độ khác dương
# lịch. Owner chốt 06/08/2026: hệ NHẬN cả 12 tháng, bốn mốc này chỉ dùng để CẢNH BÁO —
# cán bộ chịu trách nhiệm về kỳ, phần mềm không chặn (issue #66).
QUARTER_START_MONTHS = (1, 4, 7, 10)
FISCAL_START_MONTHS = tuple(range(1, 13))

# Khoản 4 Điều 12, bản thay bởi khoản 4 Điều 2 Luật 56/2024 (hiệu lực 01/01/2025): kỳ
# đầu tiên hoặc kỳ cuối cùng được gộp với kỳ kề, kỳ gộp KHÔNG QUÁ 15 tháng.
MAX_PERIOD_MONTHS = 15

# Khoảng nhãn kỳ hệ thống nhận. Không phải giới hạn nghiệp vụ, chỉ là biên chặn gõ
# nhầm (năm đầu nộp BCQT có cận dưới riêng, sớm hơn khoảng này).
YEAR_MIN, YEAR_MAX = 2015, 2030


def fiscal_bounds(period_year: int, fiscal_start_month: int) -> tuple[date, date]:
    """Cửa sổ mặc định của kỳ mang nhãn `period_year` theo niên độ DN.

    Nhãn = năm BẮT ĐẦU: niên độ tháng 4, nhãn 2025 → 01/04/2025 – 31/03/2026.
    """
    if fiscal_start_month not in FISCAL_START_MONTHS:
        raise ValueError(
            f"Tháng bắt đầu niên độ không hợp lệ: {fiscal_start_month} (chỉ nhận 1–12)"
        )
    period_from = date(period_year, fiscal_start_month, 1)
    if fiscal_start_month == 1:
        return period_from, date(period_year, 12, 31)
    end_year, end_month = period_year + 1, fiscal_start_month - 1
    return period_from, date(end_year, end_month, monthrange(end_year, end_month)[1])


def period_span_months(period_from: date, period_to: date) -> int:
    """Độ dài kỳ tính bằng tháng, tính CẢ tháng đầu và tháng cuối."""
    return (
        (period_to.year - period_from.year) * 12
        + (period_to.month - period_from.month)
        + 1
    )


def period_window_errors(
    period_year: int, period_from: date, period_to: date
) -> list[str]:
    """Lý do cửa sổ KHÔNG dùng được cho kỳ mang nhãn `period_year`. Rỗng = hợp lệ.

    Kiểm ở đây chứ không ở route, vì cửa sổ vào DB qua hai đường — cán bộ nhập tay và
    hệ suy từ tiêu đề file. Ca HIEP_QUANG (#66) đến từ đường thứ hai.
    """
    errors: list[str] = []
    if period_from > period_to:
        errors.append("Từ ngày phải nhỏ hơn hoặc bằng đến ngày.")
        return errors  # các phép đo dưới vô nghĩa khi cửa sổ ngược
    if period_to < date(period_year, 1, 1) or period_from > date(period_year, 12, 31):
        # GIAO, không phải "bắt đầu đúng năm": kỳ chuyển tiếp khi DN đổi niên độ được
        # bắt đầu từ năm trước (#49 đã chốt cảnh-báo-không-chặn cho ca đó). Ràng buộc
        # chỉ loại cửa sổ KHÔNG dính gì tới nhãn — đúng ca HIEP_QUANG nhãn 2024 mà cửa
        # sổ nằm trọn trong 2021.
        errors.append(
            f"Kỳ mang nhãn {period_year} phải có phần nằm trong năm {period_year}, "
            f"nhưng cửa sổ là {period_from.strftime('%d/%m/%Y')}"
            f"–{period_to.strftime('%d/%m/%Y')}."
        )
    span = period_span_months(period_from, period_to)
    if span > MAX_PERIOD_MONTHS:
        errors.append(
            f"Kỳ dài {span} tháng, vượt mức {MAX_PERIOD_MONTHS} tháng "
            "(khoản 4 Điều 12 Luật Kế toán, bản sửa bởi Luật 56/2024)."
        )
    return errors


def duplicate_period_windows(
    session, company_id: int, period_year: int, period_from: date, period_to: date
) -> list[int]:
    """Nhãn các kỳ KHÁC của cùng DN đang mang ĐÚNG cửa sổ này.

    Trùng khít là ca không cần định nghĩa ngưỡng cũng biết là sai: hai kỳ khác nhau
    không thể cùng một khoảng ngày. Chồng lấn một phần thì #49 đã cảnh báo, không chặn.
    """
    rows = session.execute(
        select(CompanyPeriod.period_year).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year != period_year,
            CompanyPeriod.period_from == period_from,
            CompanyPeriod.period_to == period_to,
        )
    ).all()
    return sorted(r[0] for r in rows)


def default_bounds(
    header: CompanyHeader | None, period_year: int, fiscal_start_month: int = 1
) -> tuple[date, date]:
    """Cửa sổ kỳ suy tự động: tiêu đề file khi CÓ ĐỦ cả 2 ngày, ngược lại niên độ DN."""
    period_from = header.period_from if header else None
    period_to = header.period_to if header else None
    if period_from is None or period_to is None:
        return fiscal_bounds(period_year, fiscal_start_month)
    return period_from, period_to


def period_window_conflict(
    session, company_id: int, period_year: int
) -> tuple[tuple[date, date], tuple[date, date]] | None:
    """Cửa sổ ĐANG DÙNG cho kỳ lệch với niên độ mặc định của DN → `(đang dùng, niên độ)`.

    Cửa sổ tự suy được ghi từ tiêu đề file, nên đây chính là cảnh báo "tiêu đề file
    lệch niên độ DN" đọc từ trạng thái đã lưu. Bản `is_manual` là lựa chọn có chủ ý
    của cán bộ — không cảnh báo.
    """
    month = company_fiscal_start_month(session, company_id)
    if month == 1:
        return None
    row = session.scalar(
        select(CompanyPeriod).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year == period_year,
        )
    )
    if row is None or row.is_manual or row.period_from is None or row.period_to is None:
        return None
    expected = fiscal_bounds(period_year, month)
    actual = (row.period_from, row.period_to)
    return None if actual == expected else (actual, expected)


def in_period(
    declaration_date: date | None, period_from: date, period_to: date
) -> bool:
    """Dòng BCCT thuộc kỳ khi ngày tờ khai nằm trong `[from, to]` (bao gồm biên).
    Dòng thiếu ngày → quy về kỳ đang nạp (không suy được năm)."""
    if declaration_date is None:
        return True
    return period_from <= declaration_date <= period_to


def company_fiscal_start_month(session, company_id: int) -> int:
    month = session.scalar(
        select(Company.fiscal_start_month).where(Company.id == company_id)
    )
    return month if month in FISCAL_START_MONTHS else 1


def load_period_windows(
    session, company_id: int, years: list[int] | None = None
) -> dict[int, tuple[date, date]]:
    """`{period_year: (from, to)}` CHỈ cho kỳ KHÁC dương lịch — để UI hiện nhãn kỳ
    (năm tài chính) ở nơi vốn chỉ in "Năm N". Kỳ dương lịch bỏ qua (không cần chú).

    `years` bổ sung các nhãn kỳ CHƯA có dòng `company_periods`: cửa sổ suy từ niên độ
    mặc định của DN, để màn hiện nhãn kỳ vẫn in được khoảng ngày trước lần nạp đầu.
    """
    out: dict[int, tuple[date, date]] = {}
    stored: set[int] = set()
    for r in session.scalars(
        select(CompanyPeriod).where(CompanyPeriod.company_id == company_id)
    ).all():
        stored.add(r.period_year)
        if (
            r.period_from is not None
            and r.period_to is not None
            and (r.period_from, r.period_to)
            != (date(r.period_year, 1, 1), date(r.period_year, 12, 31))
        ):
            out[r.period_year] = (r.period_from, r.period_to)

    if years:
        month = company_fiscal_start_month(session, company_id)
        if month != 1:
            for y in years:
                if y not in stored:
                    out[y] = fiscal_bounds(y, month)
    return out


def current_data_version(session, company_id: int, period_year: int) -> int:
    """`data_version` hiện tại của (DN, năm); 0 nếu chưa có dòng CompanyPeriod (WS3)."""
    row = session.scalar(
        select(CompanyPeriod.data_version).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year == period_year,
        )
    )
    return row if row is not None else 0


def resolve_period_bounds(
    session,
    company_id: int,
    period_year: int,
    header: CompanyHeader | None = None,
    rejected: list[str] | None = None,
) -> tuple[date, date]:
    """Cửa sổ dùng cho (DN, kỳ), upsert vào `company_periods`.

    `rejected` (nếu truyền) nhận câu giải thích khi cửa sổ suy từ tiêu đề file bị loại
    vì không hợp lệ — ingest in ra để cán bộ biết file nào lẫn kỳ (#66).
    """
    existing = session.scalar(
        select(CompanyPeriod).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year == period_year,
        )
    )
    if existing is not None and existing.is_manual:
        return existing.period_from, existing.period_to

    month = company_fiscal_start_month(session, company_id)
    period_from, period_to = default_bounds(header, period_year, month)

    # Tiêu đề file nói một kỳ khác hẳn → KHÔNG nhận, quay về niên độ DN. Nhận nguyên
    # là cách kỳ 2024 của HIEP_QUANG lấy cửa sổ 2021 (#66): lúc nạp bỏ sạch dòng ngày
    # 2024, lúc truy vấn `declaration_scope` kéo dòng 2021 sang.
    errors = period_window_errors(period_year, period_from, period_to)
    if errors:
        if rejected is not None:
            rejected.append(
                f"Cửa sổ suy từ tiêu đề file "
                f"({period_from.strftime('%d/%m/%Y')}–{period_to.strftime('%d/%m/%Y')}) "
                f"bị loại: {' '.join(errors)} Dùng niên độ doanh nghiệp thay thế."
            )
        period_from, period_to = fiscal_bounds(period_year, month)

    if existing is None:
        session.add(
            CompanyPeriod(
                company_id=company_id,
                period_year=period_year,
                period_from=period_from,
                period_to=period_to,
                is_manual=False,
            )
        )
    else:
        existing.period_from = period_from
        existing.period_to = period_to
    session.flush()
    return period_from, period_to
