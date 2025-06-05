#!/usr/bin/env python3
"""
GPU Diagnostic Tool for Vertex AI
Tests various GPU capabilities and logs detailed information
"""

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_command(cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, and stderr"""
    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        logger.info(f"Command exit code: {result.returncode}")
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return 124, "", f"Timeout after {timeout}s"
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return 1, "", str(e)


def check_system_info() -> Dict:
    """Gather system information"""
    info = {
        "os": platform.platform(),
        "python": sys.version,
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "environment_variables": {
            k: v
            for k, v in os.environ.items()
            if "NVIDIA" in k or "CUDA" in k or "GPU" in k
        },
    }

    # Check if running in a container
    if os.path.exists("/.dockerenv"):
        info["container"] = True
    else:
        info["container"] = False

    # Check filesystem mounts (looking for /dev/nvidia devices)
    try:
        code, stdout, stderr = run_command(["mount"])
        if code == 0:
            nvidia_mounts = [
                line for line in stdout.splitlines() if "nvidia" in line.lower()
            ]
            info["nvidia_mounts"] = nvidia_mounts
    except Exception as e:
        logger.error(f"Error checking mounts: {e}")

    return info


def check_gpu_availability() -> Dict:
    """Check if NVIDIA GPU is available using nvidia-smi"""
    gpu_info = {"available": False, "details": {}}

    code, stdout, stderr = run_command(["nvidia-smi"])
    if code == 0:
        gpu_info["available"] = True
        gpu_info["output"] = stdout

        # Get detailed GPU information
        code, stdout, stderr = run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version,cuda_version",
                "--format=csv,noheader",
            ]
        )
        if code == 0:
            parts = stdout.strip().split(",")
            if len(parts) >= 4:
                gpu_info["details"] = {
                    "name": parts[0].strip(),
                    "memory": parts[1].strip(),
                    "driver_version": parts[2].strip(),
                    "cuda_version": parts[3].strip(),
                }
    else:
        gpu_info["error"] = stderr
        gpu_info["available"] = False

    return gpu_info


def check_cuda_libraries() -> Dict:
    """Check CUDA libraries and paths"""
    cuda_info = {"found": False}

    # Check for CUDA libraries
    cuda_paths = [
        "/usr/local/cuda/lib64",
        "/usr/local/cuda/lib",
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib/nvidia",
    ]

    for path in cuda_paths:
        if os.path.exists(path):
            # Look for CUDA libraries
            libraries = [
                f
                for f in os.listdir(path)
                if f.startswith("libcuda")
                or f.startswith("libnvidia")
                or f.startswith("libcudnn")
            ]
            if libraries:
                cuda_info["found"] = True
                cuda_info["path"] = path
                cuda_info["libraries"] = libraries
                break

    # Check nvcc version if available
    code, stdout, stderr = run_command(["nvcc", "--version"])
    if code == 0:
        cuda_info["nvcc_version"] = stdout

    return cuda_info


def check_ffmpeg() -> Dict:
    """Check ffmpeg installation and capabilities"""
    ffmpeg_info = {"installed": False}

    # Check if ffmpeg is installed
    code, stdout, stderr = run_command(["ffmpeg", "-version"])
    if code == 0:
        ffmpeg_info["installed"] = True
        ffmpeg_info["version"] = (
            stdout.splitlines()[0] if stdout.splitlines() else "Unknown"
        )

        # Check encoders
        code, stdout, stderr = run_command(["ffmpeg", "-encoders"])
        if code == 0:
            encoders = stdout.splitlines()
            nvenc_encoders = [line for line in encoders if "nvenc" in line]
            ffmpeg_info["nvenc_encoders"] = nvenc_encoders
            ffmpeg_info["has_nvenc"] = len(nvenc_encoders) > 0
    else:
        ffmpeg_info["error"] = stderr

    return ffmpeg_info


def test_nvenc_encoding() -> Dict:
    """Test basic NVENC encoding with ffmpeg"""
    result = {"success": False}

    # Create a small test video
    with tempfile.NamedTemporaryFile(suffix=".mp4") as output_file:
        # Try with GPU acceleration
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=30",
            "-c:v",
            "h264_nvenc",
            "-y",
            output_file.name,
        ]

        code, stdout, stderr = run_command(cmd, timeout=60)
        if code == 0:
            result["success"] = True
            result["output_size"] = os.path.getsize(output_file.name)
            result["method"] = "gpu"
        else:
            result["error_gpu"] = stderr

            # Try with CPU encoding as fallback
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1:size=320x240:rate=30",
                "-c:v",
                "libx264",
                "-y",
                output_file.name,
            ]

            code, stdout, stderr = run_command(cmd, timeout=60)
            if code == 0:
                result["success"] = True
                result["output_size"] = os.path.getsize(output_file.name)
                result["method"] = "cpu"
            else:
                result["error_cpu"] = stderr

    return result


def check_python_dependencies() -> Dict:
    """Check Python dependencies for video processing"""
    deps = {"installed": {}}

    # Check moviepy
    try:
        import moviepy

        deps["installed"]["moviepy"] = moviepy.__version__
    except ImportError:
        deps["installed"]["moviepy"] = False

    # Check numpy
    try:
        import numpy

        deps["installed"]["numpy"] = numpy.__version__
    except ImportError:
        deps["installed"]["numpy"] = False

    # Check Pillow
    try:
        import PIL

        deps["installed"]["pillow"] = PIL.__version__

        # Check font availability
        try:
            from PIL import ImageFont

            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/app/fonts/DejaVuSans.ttf",
            ]

            fonts_found = []
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font = ImageFont.truetype(path, 12)
                        fonts_found.append(path)
                    except Exception as e:
                        fonts_found.append(f"{path} (error: {str(e)})")

            deps["fonts"] = fonts_found
        except Exception as e:
            deps["fonts_error"] = str(e)
    except ImportError:
        deps["installed"]["pillow"] = False

    # Check OpenCV
    try:
        import cv2

        deps["installed"]["opencv"] = cv2.__version__
    except ImportError:
        deps["installed"]["opencv"] = False

    return deps


def main():
    """Run all diagnostics and print results"""
    parser = argparse.ArgumentParser(description="GPU Environment Diagnostic Tool")
    parser.add_argument("--output", help="Output file for diagnostic results")
    parser.add_argument(
        "--test-encode", action="store_true", help="Test NVENC encoding"
    )
    args = parser.parse_args()

    logger.info("Starting GPU environment diagnostics")

    # Run all diagnostics
    diagnostics = {
        "system": check_system_info(),
        "gpu": check_gpu_availability(),
        "cuda": check_cuda_libraries(),
        "ffmpeg": check_ffmpeg(),
        "python_dependencies": check_python_dependencies(),
    }

    # Run encoding test if requested
    if args.test_encode:
        diagnostics["encoding_test"] = test_nvenc_encoding()

    # Print results
    print(json.dumps(diagnostics, indent=2))

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(diagnostics, f, indent=2)
        logger.info(f"Results saved to {args.output}")

    # Determine overall status
    if diagnostics["gpu"]["available"]:
        if diagnostics["ffmpeg"]["has_nvenc"]:
            logger.info("✅ GPU and NVENC are available and working correctly")
            return 0
        else:
            logger.warning("⚠️ GPU is available but NVENC is not supported in ffmpeg")
            return 1
    else:
        logger.error("❌ No GPU available - running in CPU-only mode")
        return 2


if __name__ == "__main__":
    sys.exit(main())
