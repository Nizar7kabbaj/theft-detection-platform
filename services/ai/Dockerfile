ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.11.32
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/app/.ultralytics \
    MPLCONFIGDIR=/app/.matplotlib
RUN groupadd --system --gid 1000 ai \
    && useradd --system --uid 1000 --gid 1000 --home /app ai
WORKDIR /app

FROM base AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=8
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS weights
ADD --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt /app/yolov8n-pose.pt
ADD --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt /app/yolov8n.pt

FROM base AS probe
ARG GRPC_HEALTH_PROBE_VERSION
ADD --chmod=0755 https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 /usr/local/bin/grpc_health_probe

FROM base AS runtime
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder --chown=ai:ai /opt/venv /opt/venv
COPY --from=weights --chown=ai:ai /app/yolov8n-pose.pt /app/yolov8n-pose.pt
COPY --from=weights --chown=ai:ai /app/yolov8n.pt /app/yolov8n.pt
COPY --from=probe /usr/local/bin/grpc_health_probe /usr/local/bin/grpc_health_probe
COPY --chown=ai:ai app /app/app
RUN mkdir -p /app/.ultralytics /app/.matplotlib /app/snapshots \
    && chown ai:ai /app/.ultralytics /app/.matplotlib /app/snapshots
USER ai
EXPOSE 50051 9464
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=3 \
    CMD grpc_health_probe -addr=localhost:50051 -tls -tls-ca-cert=/run/secrets/ai_tls_ca -tls-client-cert=/run/secrets/ai_tls_cert -tls-client-key=/run/secrets/ai_tls_key || exit 1
CMD ["python", "-m", "app.main"]
