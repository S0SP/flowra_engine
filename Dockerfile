# ── Flowra Engine — Production Dockerfile ─────────────────────────────────────
# Runs the Django web server via gunicorn on port 8080 (Cloud Run default).
# Build: docker build -t flowra-engine .
# Run:   docker run -p 8080:8080 --env-file .env flowra-engine

FROM python:3.11-slim

# Install system dependencies (psycopg2 needs libpq-dev)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files for whitenoise (admin, DRF browsable API)
RUN SECRET_KEY=build-time-only-placeholder python manage.py collectstatic --noinput || true

# Cloud Run listens on 8080; 2 gunicorn workers handles concurrent requests
# 120s timeout for long-running workflow executions
EXPOSE 8080
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "flowra_engine.wsgi:application"]
