# Audit-HQ MVP

Sản phẩm demo cho đề án Audit-HQ (Hệ thống Quản lý Rủi ro cho Hải quan).

Repo đề án: [TinsuAI/audit-hq](https://github.com/TinsuAI/audit-hq) — source of truth cho catalog 49 kiểm tra. Repo này (`audit-hq-mvp`) là implementation MVP (16 kiểm tra, 4 doanh nghiệp demo).

Live demo: **https://audit-hq-demo.tinsu.ai**

## Tính năng

**Quản lý doanh nghiệp**
- Tổng quan doanh nghiệp sắp xếp theo điểm rủi ro
- Tự tạo doanh nghiệp, upload file Excel BCQT, chạy lại kiểm tra qua UI
- Xem dữ liệu thô theo bảng (M15, M16, M17...) và xuất Excel

**Kiểm tra tự động**
- 16 kiểm tra MVP từ catalog 49 kiểm tra của đề án
- Phân loại 3 mức: Nghiêm trọng / Cảnh báo / Thông tin
- Combo signature: cộng thêm 20 điểm khi nhiều dấu hiệu bất thường cùng xuất hiện
- Quản lý trạng thái phát hiện (mở / đang xử lý / đã giải quyết / bỏ qua)

**AI Assistant**
- Chat sidebar (💬 góc dưới phải) với streaming SSE
- 6 tool read-only: tìm phát hiện, tra cứu dữ liệu thô, tra cứu pháp lý, giải thích kiểm tra, liệt kê DN
- Citation kèm link đến dữ liệu nguồn
- Lịch sử hội thoại, configurable qua `/admin/ai` (model, rate limit, budget cap, tool call cap...)
- Guardrails: redact forbidden phrase, cảnh báo khi thiếu citation

**Phân quyền**
- Hai role: `admin` (Tinsu) và `officer` (cán bộ HQ)
- Officer: xem DN, tạo DN, upload, chạy kiểm tra, AI chat
- Admin: tất cả quyền officer + cấu hình hệ thống (`/admin/*`)
- Quản lý tài khoản qua `/admin/users`

## Yêu cầu

- Python 3.12+
- `uv` hoặc `pip` để cài deps
- Docker + Docker Compose (cho deploy)

## Khởi động dev

```bash
make install        # cài deps vào .venv
make migrate        # tạo SQLite DB + chạy migrations
make dev            # FastAPI tại localhost:8000
```

Login mặc định (dev): `admin` / `admin` — seed từ env `AUTH_USER` / `AUTH_PASSWORD`.

## Test

```bash
make test           # pytest (190 tests)
make lint           # ruff
```

## Biến môi trường

| Biến | Mô tả | Mặc định |
|------|-------|---------|
| `AUTH_USER` | Username admin seed lần đầu | `admin` |
| `AUTH_PASSWORD` | Password admin seed lần đầu | `admin` |
| `SESSION_SECRET` | Secret key ký cookie | random (không an toàn cho prod) |
| `DATABASE_URL` | SQLite path | `sqlite:///./audit_hq.sqlite` |
| `AI_API_KEY` | OpenRouter/OpenAI key (seed lần đầu) | trống |

Các setting AI (model, budget, rate limit...) quản lý qua `/admin/ai` sau khi khởi động, không cần restart.

## Triển khai

`audit-hq-demo.tinsu.ai` — Tinsu VPS, Docker Compose, Cloudflare Tunnel. CI/CD qua GitHub Actions (self-hosted runner). Xem `.ai/STATUS.md` cho chi tiết infra.
