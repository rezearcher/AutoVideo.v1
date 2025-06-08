# -------- build stage --------
FROM python:3.11-slim as builder
WORKDIR /app

# Build time comment to force rebuild: 2025-06-08-16:45 (slim build)

# Copy requirements and install to /install prefix
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    pip install --prefix=/install --no-cache-dir "google-cloud-aiplatform[preview]>=1.96.0" \
                                          google-cloud-storage ffmpeg-python && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc && apt-get clean && rm -rf /var/lib/apt/lists/*

# -------- runtime stage --------
FROM python:3.11-slim

# Install only essential runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV TZ=UTC
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV GUNICORN_CMD_ARGS="--log-level=info --access-logfile=- --error-logfile=- --capture-output --enable-stdio-inheritance --timeout 120"
ENV VEO_MODEL=veo-3.0-generate-preview
ENV VOICE_ENABLED=false
ENV CAPTIONS_ENABLED=false

# Copy Python packages from builder stage
COPY --from=builder /install /usr/local

# Create app directory and necessary subdirectories
WORKDIR /app
RUN mkdir -p /app/output /app/secrets /app/tmp
RUN chmod 777 /app/tmp  # Ensure tmp directory is writable

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app

# Copy application code
COPY . .

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Use Hypercorn with sync workers - Cloud Run handles HTTP/2 termination
CMD ["hypercorn", "main:asgi_app", "--bind", "0.0.0.0:8080", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"] 