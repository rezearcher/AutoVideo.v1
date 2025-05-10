# Base image
FROM python:3.11-slim

# Install OS dependencies including fonts
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    build-essential \
    fonts-liberation \
    fonts-dejavu \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV TZ=UTC
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV GUNICORN_CMD_ARGS="--log-level=info --access-logfile=- --error-logfile=- --capture-output --enable-stdio-inheritance --timeout 120 --graceful-timeout 120"

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir moviepy gunicorn flask

# Create necessary directories
RUN mkdir -p /app/output /app/secrets /app/fonts

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Health check with more frequent checks during startup
HEALTHCHECK --interval=2s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Start gunicorn with explicit port binding and startup checks
CMD ["gunicorn", \
     "--bind", "0.0.0.0:${PORT}", \
     "--workers", "1", \
     "--threads", "8", \
     "--timeout", "120", \
     "--graceful-timeout", "120", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--capture-output", \
     "--enable-stdio-inheritance", \
     "--preload", \
     "main:application"] 