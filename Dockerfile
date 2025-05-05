# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install OS dependencies (ffmpeg for MoviePy, curl for debugging)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Set environment variables
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/credentials.json
ENV TZ=America/Chicago

# Create necessary directories
RUN mkdir -p /app/secrets /app/output

# Set permissions
RUN chmod -R 755 /app

# Entrypoint script
CMD ["python", "main.py"] 