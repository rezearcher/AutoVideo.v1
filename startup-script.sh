#!/bin/bash

# Install Docker
apt-get update
apt-get install -y docker.io

# Pull and run the GPU worker container
# (Assumes NVIDIA drivers and nvidia-docker are pre-installed on the image)
docker pull gcr.io/$PROJECT_ID/gpu-worker:latest
docker run -d --gpus all -p 8000:8000 gcr.io/$PROJECT_ID/gpu-worker:latest 