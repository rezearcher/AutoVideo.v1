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
ENV GUNICORN_CMD_ARGS="--log-level=info --access-logfile=- --error-logfile=- --capture-output --enable-stdio-inheritance --timeout 120"

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "moviepy==1.0.3" "decorator>=4.0.2" "imageio>=2.5" "imageio-ffmpeg>=0.4.0" "numpy>=1.17.3" "proglog<=1.0.0" "requests>=2.8.1" "tqdm>=4.11.2" && \
    pip install --no-cache-dir gunicorn flask

# Create necessary directories
RUN mkdir -p /app/output /app/secrets /app/fonts

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Start gunicorn with proper logging and increased timeout
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "--enable-stdio-inheritance", "main:application"] 