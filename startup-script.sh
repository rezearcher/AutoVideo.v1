#!/bin/bash

# Exit on error
set -e

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID is not set"
    exit 1
fi

# Install NVIDIA drivers and CUDA
echo "Installing NVIDIA drivers and CUDA..."
apt-get update
apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit

# Install Docker
echo "Installing Docker..."
apt-get install -y docker.io

# Install NVIDIA Container Toolkit
echo "Installing NVIDIA Container Toolkit..."
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update
apt-get install -y nvidia-container-toolkit
systemctl restart docker

# Wait for NVIDIA drivers to be ready
echo "Waiting for NVIDIA drivers..."
sleep 10
nvidia-smi

# Pull and run the GPU worker container
echo "Pulling GPU worker container..."
docker pull gcr.io/$PROJECT_ID/gpu-worker:latest

echo "Starting GPU worker container..."
docker run -d --gpus all -p 8000:8000 gcr.io/$PROJECT_ID/gpu-worker:latest

echo "GPU worker deployment complete!" 