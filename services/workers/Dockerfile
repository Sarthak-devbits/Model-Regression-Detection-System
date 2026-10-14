# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs/shared/pyproject.toml libs/shared/pyproject.toml
COPY services/workers/pyproject.toml services/workers/pyproject.toml
RUN uv sync --frozen --no-dev --package eval-workers --no-install-workspace

COPY libs/shared libs/shared
COPY services/workers services/workers
RUN uv sync --frozen --no-dev --package eval-workers --no-editable

FROM base AS runtime
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data \
 && chown app:app /data
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
USER app
# Compose overrides this per service with -Q eval / judge / reports.
CMD ["celery", "-A", "eval_workers.celery_app", "worker", "-Q", "eval,judge,reports", "--loglevel", "INFO"]
