FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install -U pip && pip install -e .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/audit_hq.sqlite

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
