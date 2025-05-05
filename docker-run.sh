#!/bin/bash

# Build the Docker image
echo "Building Docker image..."
docker build -t ai-video-generator .

# Run the container
echo "Running container..."
docker run -it --rm \
    -v "$(pwd)/secrets:/app/secrets" \
    -v "$(pwd)/output:/app/output" \
    ai-video-generator 