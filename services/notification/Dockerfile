ARG PYTHON_VERSION=3.11-slim
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25

FROM python:${PYTHON_VERSION} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 1000 app \
    && useradd  --system --uid 1000 --gid 1000 --shell /bin/bash --home /app app

WORKDIR /app
FROM base AS deps-server
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[server]" \
    && find /usr/local/lib/python*/site-packages -name "__pycache__" -type d -exec rm -rf {} +
FROM base AS deps-worker
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[worker]" \
    && find /usr/local/lib/python*/site-packages -name "__pycache__" -type d -exec rm -rf {} +

FROM base AS server
ARG GRPC_HEALTH_PROBE_VERSION
RUN curl -fsSL -o /usr/local/bin/grpc_health_probe \
        https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 \
    && chmod +x /usr/local/bin/grpc_health_probe

COPY --from=deps-server /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps-server /usr/local/bin /usr/local/bin
COPY --chown=app:app pyproject.toml /app/pyproject.toml
COPY --chown=app:app app/__init__.py /app/app/__init__.py
COPY --chown=app:app app/shared /app/app/shared
COPY --chown=app:app app/repositories /app/app/repositories
COPY --chown=app:app app/core /app/app/core
COPY --chown=app:app app/server /app/app/server

USER app
EXPOSE 50052 8000 9464
CMD ["python", "-m", "app.server.main"]
FROM base AS worker
COPY --from=deps-worker /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps-worker /usr/local/bin /usr/local/bin
COPY --chown=app:app pyproject.toml /app/pyproject.toml
COPY --chown=app:app app/__init__.py /app/app/__init__.py
COPY --chown=app:app app/shared /app/app/shared
COPY --chown=app:app app/repositories /app/app/repositories
COPY --chown=app:app app/core /app/app/core
COPY --chown=app:app app/worker /app/app/worker

USER app
EXPOSE 9465
CMD ["celery", "-A", "app.worker.bootstrap", "worker", "--loglevel=INFO", "--pool=solo", "--concurrency=1"]
