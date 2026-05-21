#!/usr/bin/env bash
# Container entrypoint: chạy migration rồi start uvicorn.
set -euo pipefail

echo "[entrypoint] Version: ${APP_VERSION:-}@${BUILD_SHA:-unknown} (built ${BUILD_TIME:-?})"
echo "[entrypoint] Database: ${DATABASE_URL:-?}"

# Đảm bảo DB folder exists (volume mount).
mkdir -p /db-data

# Alembic migrate (idempotent — chỉ chạy migration mới).
echo "[entrypoint] Running alembic upgrade head..."
alembic upgrade head

# Seed UOM canonical + aliases (idempotent — skip nếu đã có).
echo "[entrypoint] Seeding UOM canonical + aliases..."
python -m scripts.seed_uom

# Start uvicorn (single worker — dataset nhỏ, SQLite tránh write contention).
echo "[entrypoint] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
