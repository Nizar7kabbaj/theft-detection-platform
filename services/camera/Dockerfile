ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.32

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 1000 camera \
    && useradd --system --uid 1000 --gid 1000 --home /app camera
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

FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder --chown=camera:camera /opt/venv /opt/venv
COPY --chown=camera:camera app /app/app
USER camera
EXPOSE 9464
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD test -f /tmp/camera_heartbeat && \
        [ $(( $(date +%s) - $(stat -c %Y /tmp/camera_heartbeat) )) -lt 10 ] || exit 1
CMD ["python", "-m", "app.main"]
