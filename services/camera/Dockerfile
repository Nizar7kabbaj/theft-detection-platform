FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 camera \
    && useradd --system --uid 1000 --gid 1000 --shell /bin/bash --home /app camera

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
RUN chown -R camera:camera /app
USER camera

EXPOSE 9464

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD test -f /tmp/camera_heartbeat && \
        [ $(( $(date +%s) - $(stat -c %Y /tmp/camera_heartbeat) )) -lt 10 ] || exit 1

CMD ["python", "-m", "app.main"]
