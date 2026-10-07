ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.11.32

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
    uv sync --frozen --no-install-project --no-dev --extra server \
    && rm -f /opt/venv/.lock

FROM base AS builder-worker
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra worker \
    && rm -f /opt/venv/.lock


FROM base AS server
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder-server /opt/venv /opt/venv
COPY --chmod=u=rwX,go=rX app/__init__.py /app/app/__init__.py
COPY --chmod=u=rwX,go=rX app/shared /app/app/shared
COPY --chmod=u=rwX,go=rX app/repositories /app/app/repositories
COPY --chmod=u=rwX,go=rX app/core /app/app/core
COPY --chmod=u=rwX,go=rX app/migrations /app/app/migrations
COPY --chmod=u=rwX,go=rX app/server /app/app/server
USER app
EXPOSE 50052 8000 9464
HEALTHCHECK --interval=10s --timeout=4s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-m", "app.server.healthcheck"]
CMD ["python", "-m", "app.server.main"]

FROM base AS worker
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder-worker /opt/venv /opt/venv
COPY --chmod=u=rwX,go=rX app/__init__.py /app/app/__init__.py
COPY --chmod=u=rwX,go=rX app/shared /app/app/shared
COPY --chmod=u=rwX,go=rX app/repositories /app/app/repositories
COPY --chmod=u=rwX,go=rX app/core /app/app/core
COPY --chmod=u=rwX,go=rX app/worker /app/app/worker
COPY --chmod=u=rwX,go=rX app/telegram /app/app/telegram
COPY --chmod=u=rwX,go=rX app/server/__init__.py /app/app/server/__init__.py
COPY --chmod=u=rwX,go=rX app/server/grpc_gen /app/app/server/grpc_gen
RUN mkdir -p /app/run && chown app:app /app/run
USER app
EXPOSE 9465
HEALTHCHECK --interval=15s --timeout=3s --start-period=120s --start-interval=3s --retries=3 \
    CMD ["sh", "-c", "test $(( $(date +%s) - $(stat -c %Y /app/run/heartbeat) )) -lt 180"]
CMD ["celery", "-A", "app.worker.bootstrap", "worker", "--loglevel=INFO", "--pool=solo", "--concurrency=1"]
