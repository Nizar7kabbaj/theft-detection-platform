ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.11.32

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/app/.ultralytics \
    MPLCONFIGDIR=/app/.matplotlib
RUN groupadd --system --gid 1000 gate \
    && useradd --system --uid 1000 --gid 1000 --home /app gate
WORKDIR /app

FROM base AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=8
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS weights
ADD --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt /app/yolov8n.pt

FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder --chown=gate:gate /opt/venv /opt/venv
COPY --from=weights --chown=gate:gate /app/yolov8n.pt /app/yolov8n.pt
COPY --chown=gate:gate app /app/app
RUN mkdir -p /app/.ultralytics /app/.matplotlib \
    && chown gate:gate /app/.ultralytics /app/.matplotlib
USER gate
EXPOSE 9464
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD test -f /tmp/detect_gate_heartbeat && \
        [ $(( $(date +%s) - $(stat -c %Y /tmp/detect_gate_heartbeat) )) -lt 10 ] || exit 1
CMD ["python", "-m", "app.main"]
