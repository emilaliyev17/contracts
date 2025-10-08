# Use Python 3.13 slim image for smaller size
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Install system dependencies required for PostgreSQL, Pillow, and PDF processing
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements first for better Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Verify static files were collected (for debugging)
RUN ls -la /app/staticfiles/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (Cloud Run will override with PORT env var)
EXPOSE 8080

# Run migrations and start gunicorn
CMD python manage.py migrate --noinput && exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60 contract_analyzer.wsgi:application

