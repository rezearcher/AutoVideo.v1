"""Utilities for processing audio files."""

import json
import logging
import os
import subprocess
import tempfile
import uuid
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_audio_loudness(
    input_file: str,
    output_file: str,
    target_loudness: float = -16.0,
    target_lra: float = 11.0,
    target_tp: float = -1.0,
) -> bool:
    """
    Normalize audio loudness using FFmpeg's loudnorm filter with a two-pass approach.

    Args:
        input_file: Path to input audio file
        output_file: Path to output normalized audio file
        target_loudness: Target integrated loudness level (LUFS)
        target_lra: Target loudness range (LU)
        target_tp: Target true peak (dBTP)

    Returns:
        True if normalization was successful, False otherwise
    """
    try:
        # Create a temporary file for the first-pass measurement results
        measurements_file = f"/tmp/loudnorm_measurements_{uuid.uuid4().hex[:8]}.json"

        # First pass: analyze the audio and capture loudnorm stats
        first_pass_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_file,
            "-af",
            f"loudnorm=I={target_loudness}:LRA={target_lra}:TP={target_tp}:print_format=json",
            "-f",
            "null",
            "-",
        ]

        # Run first pass and capture the loudnorm statistics from stderr
        process = subprocess.run(
            first_pass_cmd, stderr=subprocess.PIPE, text=True, check=False
        )

        # Extract the JSON stats from stderr
        stderr_lines = process.stderr.splitlines()
        json_data = None

        # Find the JSON block in the output
        capture_json = False
        json_lines = []

        for line in stderr_lines:
            line = line.strip()
            if "loudnorm stats" in line:
                capture_json = True
                continue
            elif capture_json and line:
                if line.startswith("{") or ":" in line:
                    json_lines.append(line)
            elif capture_json and not line:
                capture_json = False

        if json_lines:
            # Join and clean up the JSON lines
            json_str = "".join(json_lines)
            # Make sure it starts and ends with braces
            if not json_str.startswith("{"):
                json_str = "{" + json_str
            if not json_str.endswith("}"):
                json_str = json_str + "}"
            # Replace any trailing commas before a closing brace
            json_str = json_str.replace(",}", "}")

            try:
                json_data = json.loads(json_str)

                # Save measurements to a file for debugging or reuse
                with open(measurements_file, "w") as f:
                    json.dump(json_data, f)

                logger.debug(f"First pass loudnorm measurements: {json_data}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing loudnorm JSON: {e}")
                logger.debug(f"Problematic JSON string: {json_str}")

        if not json_data:
            # Fall back to simple normalization if we couldn't get the measurements
            logger.warning(
                "Failed to get loudnorm measurements, using single-pass normalization"
            )
            return _normalize_audio_simple(input_file, output_file, target_loudness)

        # Second pass: apply normalization with the measured values
        second_pass_filter = (
            f"loudnorm=I={target_loudness}:LRA={target_lra}:TP={target_tp}"
            f":measured_I={json_data.get('input_i', '0')}:measured_LRA={json_data.get('input_lra', '0')}"
            f":measured_TP={json_data.get('input_tp', '0')}:measured_thresh={json_data.get('input_thresh', '0')}"
            f":offset={json_data.get('target_offset', '0')}:linear=true:print_format=summary"
        )

        second_pass_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_file,
            "-af",
            second_pass_filter,
            output_file,
        ]

        # Run second pass
        subprocess.run(second_pass_cmd, check=True, capture_output=True)

        # Clean up the measurements file
        if os.path.exists(measurements_file):
            os.remove(measurements_file)

        logger.info(
            f"Audio loudness normalized to {target_loudness} LUFS using two-pass method"
        )
        return True

    except Exception as e:
        logger.error(f"Error normalizing audio loudness: {e}")
        # Fall back to simple normalization
        return _normalize_audio_simple(input_file, output_file, target_loudness)


def _normalize_audio_simple(
    input_file: str, output_file: str, target_loudness: float = -16.0
) -> bool:
    """
    Simple one-pass audio normalization (fallback method).

    Args:
        input_file: Path to input audio file
        output_file: Path to output normalized audio file
        target_loudness: Target integrated loudness level (LUFS)

    Returns:
        True if normalization was successful, False otherwise
    """
    try:
        # Single-pass normalization
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_file,
            "-af",
            f"loudnorm=I={target_loudness}:linear=true",
            output_file,
        ]

        subprocess.run(cmd, check=True, capture_output=True)

        logger.info(
            f"Audio loudness normalized to {target_loudness} LUFS using simple method"
        )
        return True

    except Exception as e:
        logger.error(f"Error in simple audio normalization: {e}")
        return False


def extract_audio_from_video(
    video_path: str,
    output_audio_path: str,
    normalize: bool = False,
    target_loudness: float = -16.0,
) -> Optional[str]:
    """
    Extract audio track from a video file.

    Args:
        video_path: Path to the video file
        output_audio_path: Path where the extracted audio should be saved
        normalize: Whether to normalize the audio loudness
        target_loudness: Target integrated loudness level if normalizing

    Returns:
        Path to the extracted audio file or None if extraction failed
    """
    try:
        # Extract audio track
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",  # No video
            "-acodec",
            "libmp3lame",  # MP3 format
            "-q:a",
            "2",  # High quality
            output_audio_path,
        ]

        subprocess.run(cmd, check=True, capture_output=True)

        # Normalize if requested
        if normalize and os.path.exists(output_audio_path):
            normalized_path = f"{os.path.splitext(output_audio_path)[0]}_norm.mp3"
            if normalize_audio_loudness(
                output_audio_path, normalized_path, target_loudness
            ):
                # Replace original with normalized version
                os.replace(normalized_path, output_audio_path)

        logger.info(f"Audio extracted from video: {output_audio_path}")
        return output_audio_path

    except Exception as e:
        logger.error(f"Error extracting audio from video: {e}")
        return None


def merge_audio_with_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    normalize: bool = False,
    target_loudness: float = -16.0,
) -> Optional[str]:
    """
    Merge an audio file with a video, replacing the original audio track.

    Args:
        video_path: Path to the video file
        audio_path: Path to the audio file to merge
        output_path: Path where the output video should be saved
        normalize: Whether to normalize the audio loudness before merging
        target_loudness: Target integrated loudness level if normalizing

    Returns:
        Path to the output video or None if merging failed
    """
    try:
        # Normalize audio if requested
        input_audio = audio_path
        if normalize:
            normalized_audio = f"/tmp/normalized_{uuid.uuid4().hex[:8]}.mp3"
            if normalize_audio_loudness(audio_path, normalized_audio, target_loudness):
                input_audio = normalized_audio

        # Merge audio with video
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-i",
            input_audio,
            "-c:v",
            "copy",  # Copy video stream
            "-map",
            "0:v",  # Use video from first input
            "-map",
            "1:a",  # Use audio from second input
            "-shortest",  # End when the shortest input ends
            output_path,
        ]

        subprocess.run(cmd, check=True, capture_output=True)

        # Clean up temporary file
        if normalize and os.path.exists(normalized_audio):
            os.remove(normalized_audio)

        logger.info(f"Audio merged with video: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error merging audio with video: {e}")
        return None
