ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.11.32
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid 1000 --home /app app
WORKDIR /app

FROM base AS builder-server
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra server

FROM base AS builder-worker
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra worker

FROM base AS probe
ARG GRPC_HEALTH_PROBE_VERSION
ADD --chmod=0755 https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 /usr/local/bin/grpc_health_probe

FROM base AS server
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder-server --chown=app:app /opt/venv /opt/venv
COPY --from=probe /usr/local/bin/grpc_health_probe /usr/local/bin/grpc_health_probe
COPY --chown=app:app app/__init__.py /app/app/__init__.py
COPY --chown=app:app app/shared /app/app/shared
COPY --chown=app:app app/repositories /app/app/repositories
COPY --chown=app:app app/core /app/app/core
COPY --chown=app:app app/migrations /app/app/migrations
COPY --chown=app:app app/server /app/app/server
USER app
EXPOSE 50052 8000 9464
CMD ["python", "-m", "app.server.main"]

FROM base AS worker
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder-worker --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app app/__init__.py /app/app/__init__.py
COPY --chown=app:app app/shared /app/app/shared
COPY --chown=app:app app/repositories /app/app/repositories
COPY --chown=app:app app/core /app/app/core
COPY --chown=app:app app/worker /app/app/worker
USER app
EXPOSE 9465
CMD ["celery", "-A", "app.worker.bootstrap", "worker", "--loglevel=INFO", "--pool=solo", "--concurrency=1"]
