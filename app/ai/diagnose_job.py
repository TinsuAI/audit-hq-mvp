"""Job `ai_diagnose` — chẩn đoán cấu trúc file bằng LLM, chạy ở worker.

Lời gọi này mất ~120 s với bộ file 006 (đọc lại từng file lỗi rồi hỏi model), còn
Cloudflare cắt kết nối ở 100 giây. Chạy trong request là cán bộ luôn gặp 524 đúng
lúc file đọc lỗi và cần chẩn đoán nhất. Cùng cách sửa như việc nạp (#74): route xếp
job, worker gọi LLM, `/jobs/{id}` hiện kết quả.

Thuộc `AI_JOB_KINDS` nên worker AI riêng nhận, hàng đợi chạy kiểm tra không phải chờ.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company
from app.settings import settings


def run_diagnose_job(payload: dict, db: Session) -> dict:
    """Handler job `ai_diagnose`. `result` hiện nguyên trên `/jobs/{id}` cho mọi cán
    bộ nên chỉ chứa văn bản chẩn đoán, KHÔNG chứa token/chi phí."""
    code = payload["company_code"]
    year = int(payload["year"])
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise ValueError(f"Không tìm thấy doanh nghiệp {code}")

    raw_root = Path(settings.raw_data_path)
    from app.ai import ingest_doctor

    try:
        ai_result = ingest_doctor.diagnose_with_ai(company.code, year, raw_root)
    except Exception as e:  # noqa: BLE001 — AI lỗi thành kết quả đọc được, không thành job đỏ
        # Job KHÔNG fail: cán bộ cần đọc được lý do ngay trên trang công việc, còn
        # bản thân việc "AI không trả lời" không phải hỏng hệ thống.
        ai_result = f"Không gọi được AI: {type(e).__name__}: {e}"

    return {"company_code": code, "year": year, "ai_result": ai_result}
