#!/usr/bin/env python3
"""
GPU Worker Environment Diagnostic Tool
Checks dependencies, GPU availability, and FFmpeg functionality
"""

import os
import subprocess
import sys
import traceback
from pathlib import Path

print("========== GPU WORKER DIAGNOSTIC TOOL ==========")
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")

# Check environment variables
print("\n----- Environment Variables -----")
for key, value in os.environ.items():
    if any(
        x in key.lower() for x in ["nvidia", "cuda", "gpu", "python", "path", "veo"]
    ):
        print(f"{key}: {value}")

# Check NVIDIA/GPU availability
print("\n----- GPU Detection -----")
try:
    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print("NVIDIA GPU detected:")
        print(result.stdout[:500])  # Print first 500 chars
    else:
        print(f"nvidia-smi failed with code {result.returncode}: {result.stderr}")
except Exception as e:
    print(f"Error checking GPU: {e}")

# Check CUDA libraries
print("\n----- CUDA Libraries -----")
try:
    import torch

    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA device count: {torch.cuda.device_count()}")
    if torch.cuda.is_available():
        print(f"CUDA device name: {torch.cuda.get_device_name(0)}")
except ImportError:
    print("PyTorch not installed")
except Exception as e:
    print(f"Error checking CUDA: {e}")

# Check FFMPEG
print("\n----- FFMPEG Check -----")
try:
    result = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        print("FFMPEG installed:")
        print(result.stdout.split("\n")[0])  # First line only

        # Check NVENC support
        result = subprocess.run(
            ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10
        )
        if "h264_nvenc" in result.stdout:
            print("NVENC encoder available (h264_nvenc)")
        else:
            print("NVENC encoder NOT available")
    else:
        print(f"ffmpeg check failed with code {result.returncode}: {result.stderr}")
except Exception as e:
    print(f"Error checking FFMPEG: {e}")

# Check Python dependencies
print("\n----- Python Dependencies -----")
dependencies = [
    "numpy",
    "PIL",
    "google.cloud.storage",
    "google.cloud.aiplatform",
    "vertexai.preview.generative_models",
    "cv2",
]

for dep in dependencies:
    try:
        if "." in dep:
            # For packages with submodules
            parts = dep.split(".")
            module = __import__(parts[0])
            for part in parts[1:]:
                module = getattr(module, part)
            print(f"✅ {dep} - Available")
        else:
            # For simple imports
            module = __import__(dep)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {dep} - Version: {version}")
    except ImportError:
        print(f"❌ {dep} - Not installed")
    except Exception as e:
        print(f"❌ {dep} - Error: {e}")

# Test minimal FFmpeg operation
print("\n----- FFmpeg Basic Test -----")
try:
    # Create a test file
    test_path = "/tmp/test_clip.mp4"
    print(f"Attempting to create a test file using FFmpeg at {test_path}...")

    # Generate a test video (solid color with text)
    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=640x480:d=1",
        "-vf",
        "drawtext=text='Test':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=(h-text_h)/2",
        "-t",
        "1",
        "-y",
        test_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(test_path):
        print(f"✅ Successfully wrote test clip ({os.path.getsize(test_path)} bytes)")
    else:
        print("❌ Failed to write test clip - file not created")
except Exception as e:
    print(f"❌ FFmpeg test failed: {e}")
    print(traceback.format_exc())

print("\n========== DIAGNOSTIC COMPLETE ==========")
