# ==============================================================================
# IRIS — Backend Production Dockerfile (FastAPI + SQLite + Alembic)
# ==============================================================================
FROM python:3.12-slim

# System setup & environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    DATABASE_URL=sqlite:////app/data/iris.db \
    ENVIRONMENT=production

# Install curl for container health check
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create dedicated non-root application user
RUN groupadd -g 1000 iris && \
    useradd -u 1000 -g iris -s /bin/bash -m iris

# Create persistent data directory with correct ownership
RUN mkdir -p /app/data && \
    chown -R iris:iris /app

# Install Python production dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source, migrations, and entrypoint
COPY --chown=iris:iris app/ /app/app/
COPY --chown=iris:iris alembic/ /app/alembic/
COPY --chown=iris:iris alembic.ini /app/alembic.ini
COPY --chown=iris:iris scripts/ /app/scripts/
COPY --chown=iris:iris entrypoint.sh /app/entrypoint.sh

# Ensure entrypoint is executable
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER iris

EXPOSE 8000

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
