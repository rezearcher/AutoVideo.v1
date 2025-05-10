# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install OS dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    build-essential \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
    moviepy==1.0.3 \
    gunicorn==21.2.0 \
    flask==3.0.2

# Copy code
COPY . .

# Set environment variables
ENV TZ=America/Chicago
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Create necessary directories and set permissions
RUN mkdir -p /app/secrets /app/output /app/fonts && \
    chmod -R 755 /app && \
    chown -R nobody:nogroup /app && \
    chmod -R 777 /app/output /app/secrets

# Switch to non-root user
USER nobody

# Add health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Start with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "--log-level", "info", "main:application"] 