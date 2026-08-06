"""Đoán `companies.first_bcqt_year` = kỳ quyết toán sớm nhất đang có dữ liệu.

ĐÂY LÀ PHỎNG ĐOÁN, KHÔNG PHẢI SỐ LIỆU. Ticket #57 cố ý để trống trường này: kỳ sớm
nhất trong hệ thống chỉ là biên của CỬA SỔ NẠP, không phải năm đầu doanh nghiệp nộp
BCQT. Doanh nghiệp nộp từ 2018 mà mình mới nạp từ 2023 thì đoán ra 2023, sai 5 năm.

Hệ quả phải biết trước khi chạy: trường này là cổng kỳ biên của C4.3
(`app/checks/norm_gate.py`). Đang trống thì kỳ sớm nhất của mỗi doanh nghiệp trả
*chưa đánh giá được* — vì không phân biệt được "chưa từng khai định mức" với "đã
khai trước cửa sổ dữ liệu mình có". Điền vào là khẳng định vế sau không xảy ra, cổng
mở, và C4.3 sinh phát hiện ở đúng những kỳ đang được giữ lại.

Cơ sở đoán: kỳ nhỏ nhất có dòng ở BA bảng quyết toán (Mẫu 15 / 15a / 16). KHÔNG tính
BCCT — tờ khai không phải báo cáo quyết toán, và cửa sổ tờ khai còn rộng hơn.

Usage:
    python -m scripts.seed_first_bcqt_year --report     # chỉ in, không ghi
    python -m scripts.seed_first_bcqt_year              # ghi cho DN đang trống
    python -m scripts.seed_first_bcqt_year --overwrite  # ghi đè cả DN đã có giá trị
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

# Tra `SessionLocal` qua module lúc CHẠY, không `from ... import` lúc nạp: import kéo
# theo engine đang bind ở thời điểm nạp, nên test đổi engine xong vẫn ghi vào DB cũ và
# khẳng định trên DB rỗng — script ghi thẳng vào prod thì không được có lớp đó.
import app.database as db
from app.models import Company, Norm, NvlBalance, SpBalance

_SETTLEMENT_MODELS = (NvlBalance, SpBalance, Norm)


def earliest_settlement_year(session, company_id: int) -> int | None:
    """Kỳ nhỏ nhất có dòng ở bất kỳ bảng quyết toán nào. None = chưa nạp gì."""
    years = [
        session.scalar(
            select(func.min(model.period_year)).where(model.company_id == company_id)
        )
        for model in _SETTLEMENT_MODELS
    ]
    present = [y for y in years if y is not None]
    return min(present) if present else None


def settlement_years(session, company_id: int) -> list[int]:
    """Mọi kỳ có dữ liệu quyết toán — in ra để người đọc tự thấy đoán có hợp lý không."""
    found: set[int] = set()
    for model in _SETTLEMENT_MODELS:
        found.update(
            y for (y,) in session.execute(
                select(model.period_year)
                .where(model.company_id == company_id)
                .distinct()
            ).all()
        )
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="Chỉ in, không ghi.")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Ghi đè cả doanh nghiệp đã có giá trị (mặc định chỉ điền chỗ trống).",
    )
    parser.add_argument("--company", help="Mã lưu trữ của 1 DN (để trống = tất cả).")
    args = parser.parse_args(argv)

    with db.SessionLocal() as session:
        q = select(Company).order_by(Company.code)
        if args.company:
            q = q.where(Company.code == args.company)
        companies = session.scalars(q).all()

        planned: list[tuple[Company, int]] = []
        print(f"{'Doanh nghiệp':16} {'đang có':>9} {'sẽ đặt':>8}  các kỳ có dữ liệu quyết toán")
        for company in companies:
            years = settlement_years(session, company.id)
            guess = earliest_settlement_year(session, company.id)
            current = company.first_bcqt_year
            if guess is None:
                note = "— không có dữ liệu quyết toán, bỏ qua"
                new = "—"
            elif current is not None and not args.overwrite:
                note = f"{years} — đã có giá trị, giữ nguyên"
                new = "—"
            else:
                note = str(years)
                new = str(guess)
                planned.append((company, guess))
            print(f"{company.code:16} {str(current or '—'):>9} {new:>8}  {note}")

        print()
        if not planned:
            print("Không có doanh nghiệp nào cần điền.")
            return 0
        if args.report:
            print(f"[report] {len(planned)} doanh nghiệp sẽ được điền. Chưa ghi gì.")
            return 0

        for company, guess in planned:
            company.first_bcqt_year = guess
        session.commit()
        print(f"Đã điền {len(planned)} doanh nghiệp.")
        print(
            "Kết quả kiểm tra CHƯA đổi theo: cổng kỳ biên của C4.3 đọc trường này lúc "
            "chạy. Chạy lại kiểm tra rồi mới đọc số."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
