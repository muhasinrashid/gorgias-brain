FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy contents into specific backend directory to preserve package structure
WORKDIR /app
COPY . /app/backend/

# Set Python path so it can find 'backend' module
ENV PYTHONPATH=/app

# Expose port (Railway sets PORT env var)
ENV PORT=8000
EXPOSE 8000

# Run the application using the full module path
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
