ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.32

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
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev \
    && rm -f /opt/venv/.lock

FROM base AS runtime
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder /opt/venv /opt/venv
COPY --chmod=u=rwX,go=rX app /app/app
COPY --chmod=u=rwX,go=rX tools /app/tools
COPY --chmod=u=rwX,go=rX alembic.ini /app/alembic.ini
COPY --chmod=u=rwX,go=rX migrations /app/migrations
USER audit
EXPOSE 50054
HEALTHCHECK --interval=10s --timeout=4s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]
CMD ["python", "-m", "app.main"]
