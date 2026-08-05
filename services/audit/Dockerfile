ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.32
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 1000 audit \
    && useradd --system --uid 1000 --gid 1000 --home /app audit
WORKDIR /app

FROM base AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS probe
ARG GRPC_HEALTH_PROBE_VERSION
ADD --chmod=0755 https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 /usr/local/bin/grpc_health_probe

FROM base AS runtime
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder --chown=audit:audit /opt/venv /opt/venv
COPY --from=probe /usr/local/bin/grpc_health_probe /usr/local/bin/grpc_health_probe
COPY --chown=audit:audit app /app/app
COPY --chown=audit:audit alembic.ini /app/alembic.ini
COPY --chown=audit:audit migrations /app/migrations
USER audit
EXPOSE 50054
CMD ["python", "-m", "app.main"]
