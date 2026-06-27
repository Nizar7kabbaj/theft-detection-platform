FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 alert \
    && useradd  --system --uid 1000 --gid 1000 --shell /bin/bash --home /app alert

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-dev.txt && \
    opentelemetry-bootstrap -a install

ARG GRPC_HEALTH_PROBE_VERSION=v0.4.25
RUN curl -L -o /usr/local/bin/grpc_health_probe \
        https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 \
    && chmod +x /usr/local/bin/grpc_health_probe

COPY app /app/app
COPY pyproject.toml /app/pyproject.toml

RUN chown -R alert:alert /app

USER alert

EXPOSE 50052 8000 9464

CMD ["python", "-m", "app.main"]
