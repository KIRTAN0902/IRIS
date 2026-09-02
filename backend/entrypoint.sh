#!/bin/sh
set -e

echo "[IRIS] Initializing IRIS backend container..."

# Ensure persistent data directory exists
mkdir -p /app/data

# Run Alembic migrations to current head
echo "[IRIS] Executing database schema migrations (alembic upgrade head)..."
alembic upgrade head

echo "[IRIS] Migrations complete. Starting FastAPI ASGI server on port 8000..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "*"
