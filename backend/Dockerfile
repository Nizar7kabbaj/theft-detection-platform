# Backend Dockerfile - TDP-37
# Slim Python 3.11 image for FastAPI service.
# AI libraries (torch, ultralytics, opencv) intentionally NOT installed -
# the backend only handles HTTP, MongoDB, and Telegram.

FROM python:3.11-slim

# Don't write .pyc files, don't buffer stdout (logs appear immediately)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install requirements first (separate layer = cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

EXPOSE 8000

# Production-style start: no --reload, listens on all interfaces
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]