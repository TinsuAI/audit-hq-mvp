"""Nhãn tiếng Việt cho `job.result` — trang công việc thôi in JSON thô.

Khoá trong `result` là ĐỊNH DANH nội bộ (`total_findings`, `combos_fired`) nên
giữ tiếng Anh cho khớp phần còn lại của mã nguồn; chỗ chuyển sang tiếng Việt là
lúc render. `tests/test_jobs/test_result_labels.py` khẳng định mọi khoá do
handler sinh ra đều có nhãn ở đây, nên nhánh fallback không chạy trong thực tế.
"""

from __future__ import annotations

JOB_KIND_LABEL_VI: dict[str, str] = {
    "run_checks": "Chạy kiểm tra",
    "ingest_and_run": "Nạp dữ liệu và chạy kiểm tra",
    "batch_run": "Chạy kiểm tra mọi năm",
    "ai_overview": "Tạo tổng quan AI",
    "ai_overview_batch": "Tạo tổng quan AI hàng loạt",
}

RESULT_LABEL_VI: dict[str, str] = {
    # chung
    "company_code": "Doanh nghiệp",
    "period_year": "Năm",
    "year": "Năm",
    "note": "Ghi chú",
    # run_checks / run_batch
    "company_type": "Loại hình",
    "only": "Kiểm tra đã chọn",
    "total_findings": "Tổng số phát hiện",
    "findings_per_check": "Phát hiện theo kiểm tra",
    "combos_fired": "Tổ hợp rủi ro đã kích hoạt",
    "risk_score": "Điểm rủi ro",
    "years_processed": "Các năm đã chạy",
    "per_year": "Chi tiết theo năm",
    # ai_overview
    "check_code": "Mã kiểm tra",
    "chars": "Độ dài nhận định (ký tự)",
    # ai_overview_batch
    "created": "Số kiểm tra đã tạo tổng quan",
    "skipped": "Số kiểm tra bỏ qua",
    "skipped_fresh": "Trong đó, bỏ qua vì tổng quan còn mới",
    "skipped_not_reached": "Trong đó, bỏ qua vì chưa tới lượt",
    "failed": "Số kiểm tra lỗi",
    "created_checks": "Danh sách kiểm tra đã tạo tổng quan",
    "failed_checks": "Danh sách kiểm tra lỗi",
    "stopped_reason": "Lý do dừng",
}

EMPTY = "—"


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "Có" if value else "Không"
    return str(value)


def _format(value: object) -> str:
    """Một giá trị `result` thành chuỗi đọc được. Rỗng/None → dấu gạch."""
    if value is None or value == "" or value == [] or value == {}:
        return EMPTY
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            # dict lồng (vd `per_year`) → trải một cấp, không in JSON.
            sep = " — " if isinstance(v, dict) else ": "
            parts.append(f"{k}{sep}{_format(v)}")
        return " · ".join(parts)
    if isinstance(value, list | tuple):
        return ", ".join(_format(v) for v in value)
    return _scalar(value)


def describe_result(result: dict | None) -> list[dict[str, str]]:
    """`job.result` → danh sách dòng `{label, value}` cho bảng trên giao diện.

    Khoá lạ (handler mới quên khai nhãn) vẫn hiện, lấy chính khoá làm nhãn —
    thà thô còn hơn mất dữ liệu cán bộ cần đọc.
    """
    if not result:
        return []
    return [
        {"label": RESULT_LABEL_VI.get(key, key), "value": _format(value)}
        for key, value in result.items()
    ]
