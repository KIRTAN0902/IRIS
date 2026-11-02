FROM python:3.11-slim-bookworm

# System dependencies: Git, Node.js 20, build tools, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements and Google Antigravity
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user with home directory and workspace
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/workspaces && \
    chown -R appuser:appuser /app

USER appuser
ENV HOME=/home/appuser
ENV PATH="/home/appuser/.local/bin:$PATH"

COPY --chown=appuser:appuser . /app/

# Expose default Hugging Face Spaces port
EXPOSE 7860

# Run FastAPI companion
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
