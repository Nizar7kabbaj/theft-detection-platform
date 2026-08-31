ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.11.32

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 1000 api \
    && useradd --system --uid 1000 --gid 1000 --home /app api
WORKDIR /app

FROM base AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS runtime
ENV PATH=/opt/venv/bin:$PATH
COPY --from=builder --chown=api:api /opt/venv /opt/venv
COPY --chown=api:api app /app/app
USER api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    COVERAGE_FILE=/tmp/.coverage \
    PATH=/opt/venv/bin:$PATH
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra dev
COPY --chown=api:api pyproject.toml /app/pyproject.toml
COPY --chown=api:api app /app/app
COPY --chown=api:api tests /app/tests
USER api
CMD ["pytest", "-m", "integration"]
