"""Kết quả đã lưu có còn khớp phiên bản dữ liệu không (#90).

Phép so DUY NHẤT: `check_runs.data_version` so với `CompanyPeriod.data_version`.
Trước vé này nó chỉ phục vụ tổng quan AI (`overview_is_stale`); ở đây nó thành hàm
dùng chung cho phát hiện và điểm rủi ro, không viết lại lần thứ hai.

**Hai trục, không trộn.**

- Trục BỘ FILE (`app.pipeline.readiness`): dòng Tầng 1 không còn khớp bản ghi file
  của kỳ → nạp lại.
- Trục KẾT QUẢ (ở đây): phát hiện và điểm tính trên phiên bản dữ liệu cũ hơn hiện
  tại → chạy lại kiểm tra.

Sau khi xoá file thì cả hai cùng bật; nạp lại xong chỉ còn trục kết quả, cho tới
khi cán bộ bấm chạy kiểm tra.

**Hiện nhãn, KHÔNG tự chạy lại.** `run_checks` xoá rồi dựng lại `Finding`, đưa
`status`/`notes` cán bộ đã đánh về "mới" (ADR #24). **Và không giấu số:** doanh
nghiệp có kết quả cũ vẫn nằm trong bảng xếp hạng, chỉ mang thêm nhãn — rơi khỏi
xếp hạng vì có người tải file lên là cùng dạng sai lầm với việc bỏ luật khỏi thang
điểm (#65).

Lần chạy MỚI NHẤT còn ở sau phiên bản hiện tại là đủ để kỳ đó cũ: chạy lại một mã
lẻ để lại điểm gộp phát hiện của hai phiên bản dữ liệu. Kỳ KHÔNG có dòng
`check_runs` nào thì "chưa rõ", KHÔNG phải cũ (WS3).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CheckRun, CompanyPeriod
from app.pipeline.period import current_data_version


def data_version_moved(based_on: int | None, current: int) -> bool:
    """Phiên bản dữ liệu đã dời kể từ lúc kết quả được sinh ra."""
    return current > (based_on or 0)


def results_stale(session: Session, company_id: int, period_year: int) -> bool:
    """Phát hiện và điểm của (DN, kỳ) có tính trên bộ dữ liệu cũ không."""
    based_on = session.scalar(
        select(func.min(CheckRun.data_version)).where(
            CheckRun.company_id == company_id,
            CheckRun.period_year == period_year,
        )
    )
    if based_on is None:
        return False
    return data_version_moved(
        based_on, current_data_version(session, company_id, period_year)
    )


def stale_result_years(
    session: Session, company_ids: Iterable[int] | None = None
) -> dict[int, tuple[int, ...]]:
    """`{company_id: (kỳ có kết quả cũ, …)}` — hai truy vấn cho cả bảng danh sách.

    Chỉ có mặt doanh nghiệp có ít nhất một kỳ cũ; doanh nghiệp vắng nghĩa là mọi kỳ
    đã chạy đều khớp phiên bản dữ liệu hiện tại.
    """
    ids = list(company_ids) if company_ids is not None else None
    if ids is not None and not ids:
        return {}

    runs_stmt = (
        select(
            CheckRun.company_id,
            CheckRun.period_year,
            func.min(CheckRun.data_version),
        )
        .group_by(CheckRun.company_id, CheckRun.period_year)
    )
    versions_stmt = select(
        CompanyPeriod.company_id, CompanyPeriod.period_year, CompanyPeriod.data_version
    )
    if ids is not None:
        runs_stmt = runs_stmt.where(CheckRun.company_id.in_(ids))
        versions_stmt = versions_stmt.where(CompanyPeriod.company_id.in_(ids))

    current = {
        (cid, year): version
        for cid, year, version in session.execute(versions_stmt).all()
    }
    out: dict[int, list[int]] = {}
    for cid, year, based_on in session.execute(runs_stmt).all():
        if data_version_moved(based_on, current.get((cid, year), 0)):
            out.setdefault(cid, []).append(year)
    return {cid: tuple(sorted(years)) for cid, years in out.items()}


__all__ = ["data_version_moved", "results_stale", "stale_result_years"]
