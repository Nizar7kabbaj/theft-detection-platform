FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    YOLO_CONFIG_DIR=/app/.ultralytics

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 ai \
    && useradd  --system --uid 1000 --gid 1000 --shell /bin/bash --home /app ai

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
        -r /app/requirements.txt

RUN mkdir -p /app/.ultralytics \
    && curl -L -o /app/yolov8n-pose.pt \
        https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt

ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25
RUN curl -L -o /usr/local/bin/grpc_health_probe \
        https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 \
    && chmod +x /usr/local/bin/grpc_health_probe

COPY app /app/app

RUN chown -R ai:ai /app

USER ai

EXPOSE 50051 9464

CMD ["python", "-m", "app.main"]
