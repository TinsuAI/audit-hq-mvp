# Audit-HQ MVP

Sản phẩm demo cho đề án Audit-HQ (Hệ thống Quản lý Rủi ro cho Hải quan).

Repo đề án: [TinsuAI/audit-hq](https://github.com/TinsuAI/audit-hq) — source of truth cho catalog 49 kiểm tra. Repo này (`audit-hq-mvp`) là implementation 10 tuần (16 kiểm tra MVP, 5 doanh nghiệp demo).

## Yêu cầu

- Python 3.12+
- `uv` hoặc `pip` để cài deps
- Docker + Docker Compose (cho deploy)
- Dữ liệu nền: symlink `data/` tới `../audit-hq/data/raw/` (xem `data/README.md` của repo đề án)

## Khởi động dev

```bash
make install        # cài deps vào .venv
make migrate        # tạo SQLite DB
make dev            # chạy FastAPI tại localhost:8000
```

Login mặc định (chỉ dev): `admin` / `admin` — thay bằng env vars trong demo.

## Test

```bash
make test           # pytest
make lint           # ruff
```

## Lộ trình

Xem `.ai/STATUS.md` cho trạng thái hiện tại và `audit-hq/.ai/sessions/2026-05-21-demo-plan.md` cho lộ trình 10 tuần.

## Triển khai demo

`audit-hq-demo.tinsu.ai` (Tinsu VPS, Cloudflare Tunnel, basic-auth).
