# Stage 1: build the React app. Only package files first, so dependency layers cache.
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG SPARK_SPA_BASE=/app/
ENV SPARK_SPA_BASE=$SPARK_SPA_BASE
RUN npm run build

# Stage 2: the Python app, serving the built frontend from frontend/dist.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev
COPY --from=frontend /fe/dist ./frontend/dist

RUN useradd -m spark && mkdir -p /data/media && chown -R spark:spark /data /app
USER spark
ENV PATH="/app/.venv/bin:$PATH" SPARK_MEDIA_DIR=/data/media SPARK_SPA_DIR=/app/frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["sh", "-c", "alembic upgrade head && spark serve --port 8000"]
