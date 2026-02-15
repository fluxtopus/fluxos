FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY apps/inkpass/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional shared Stripe integration package
COPY packages/aios-stripe /tmp/aios-stripe
RUN pip install --no-cache-dir /tmp/aios-stripe && rm -rf /tmp/aios-stripe

# Mimic SDK (service-to-service notifications)
COPY packages/mimic-sdk-python /tmp/mimic-sdk-python
RUN pip install --no-cache-dir /tmp/mimic-sdk-python && rm -rf /tmp/mimic-sdk-python

# Copy application code
COPY apps/inkpass/ .
RUN chmod +x start.sh

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
