FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    ca-certificates \
    redis-tools \
    # Dependencies for browser automation
    wget \
    gnupg \
    # Required for Playwright/browser-use
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxfixes3 \
    libxshmfence1 \
    libdrm2 \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy local monorepo packages first so editable requirements resolve.
# requirements.txt references ../../packages/* from /app, which resolves to /packages.
COPY packages/ /packages/

# Copy requirements for dependency installation
COPY apps/tentackl/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its browsers for browser-use
RUN pip install playwright && playwright install chromium

# Copy application code
COPY apps/tentackl/ .

# Create necessary directories
RUN mkdir -p /app/logs /app/data

# Make start scripts executable
RUN chmod +x start.sh start-worker.sh start-beat.sh

# Set Python path
ENV PYTHONPATH=/app

# Default command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
