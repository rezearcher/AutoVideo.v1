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
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "moviepy==1.0.3" "decorator>=4.0.2" "imageio>=2.5" "imageio-ffmpeg>=0.4.0" "numpy>=1.17.3" "proglog<=1.0.0" "requests>=2.8.1" "tqdm>=4.11.2"

# Create necessary directories
RUN mkdir -p /app/output /app/secrets /app/fonts

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the script directly
CMD ["python", "main.py"] 