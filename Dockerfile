FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Ho_Chi_Minh

# Locale UTF-8 cho output Vietnamese.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

WORKDIR /app

COPY pyproject.toml VERSION ./
RUN pip install -U pip && pip install -e .

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

# Build-time metadata (inject từ docker build --build-arg).
ARG BUILD_SHA=unknown
ARG BUILD_TIME=
ENV BUILD_SHA=${BUILD_SHA}
ENV BUILD_TIME=${BUILD_TIME}

RUN mkdir -p /db-data
ENV DATABASE_URL=sqlite:////db-data/audit_hq.sqlite

EXPOSE 8000

# Entry: chạy migration + start server.
COPY deploy/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
