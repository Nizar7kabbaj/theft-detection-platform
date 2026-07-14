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

RUN groupadd --system --gid 1000 gate \
    && useradd  --system --uid 1000 --gid 1000 --shell /bin/bash --home /app gate

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
        -r /app/requirements.txt
RUN mkdir -p /app/.ultralytics \
    && curl -L -o /app/yolov8n.pt \
        https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt

COPY app /app/app
RUN chown -R gate:gate /app
USER gate
EXPOSE 9464

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD test -f /tmp/detect_gate_heartbeat && \
        [ $(( $(date +%s) - $(stat -c %Y /tmp/detect_gate_heartbeat) )) -lt 10 ] || exit 1
CMD ["python", "-m", "app.main"]
