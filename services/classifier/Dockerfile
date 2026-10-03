# syntax=docker/dockerfile:1

# ---------- base: shared by both stages ----------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---------- builder: installs dependencies into /opt/venv ----------
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app

# 1) Only the manifests and the lockfile, so this layer is cached until dependencies change.
COPY pyproject.toml uv.lock ./
COPY libs/shared/pyproject.toml libs/shared/pyproject.toml
COPY services/classifier/pyproject.toml services/classifier/pyproject.toml
RUN uv sync --frozen --no-dev --package classifier-service --no-install-workspace

# 2) Now our own code, installed as normal (non-editable) packages.
COPY libs/shared libs/shared
COPY services/classifier services/classifier
RUN uv sync --frozen --no-dev --package classifier-service --no-editable

# ---------- runtime: small image with just Python and the venv ----------
FROM base AS runtime
RUN useradd --create-home --uid 10001 app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
USER app
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz', timeout=2)"]
CMD ["uvicorn", "classifier_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
