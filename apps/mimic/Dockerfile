FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY apps/mimic/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional shared Stripe integration package
COPY packages/fluxos-stripe /tmp/fluxos-stripe
RUN pip install --no-cache-dir /tmp/fluxos-stripe && rm -rf /tmp/fluxos-stripe

# Copy application code
COPY apps/mimic/ .
RUN chmod +x start.sh && chmod +x start-worker.sh

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
