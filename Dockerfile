FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[trade]" || true
COPY . ./
RUN pip install --no-cache-dir -e ".[trade]"

# Logs dir is a volume — runtime appends to it from a non-root UID.
RUN useradd --system --uid 10001 --create-home polyflow \
    && mkdir -p /app/logs \
    && chown -R polyflow:polyflow /app
USER polyflow

EXPOSE 8642

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8642/healthz || exit 1

CMD ["polyflow", "run", "--config", "/app/configs/policy.yaml", "--log", "/app/logs/immutable.jsonl", "--db", "/app/logs/polyflow.db"]
