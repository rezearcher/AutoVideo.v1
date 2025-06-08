import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_audio_loudness(
    input_path: str,
    output_path: str,
    target_loudness: float = -16.0,
    true_peak: float = -1.5,
    loudness_range: float = 11.0,
) -> bool:
    """
    Normalize audio loudness to broadcast standards using FFmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        target_loudness: Target integrated loudness in LUFS (Loudness Units Full Scale)
        true_peak: Maximum true peak level in dBTP (decibels True Peak)
        loudness_range: Target loudness range in LU (Loudness Units)

    Returns:
        True if normalization was successful, False otherwise
    """
    try:
        # Ensure input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False

        # Create temporary file for the normalized audio
        temp_output = f"{output_path}.temp.wav"

        # Build FFmpeg command with loudnorm filter
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output files without asking
            "-i",
            input_path,
            "-probesize",
            "50M",  # Increase probe size for better loudness analysis
            "-af",
            f"loudnorm=I={target_loudness}:TP={true_peak}:LRA={loudness_range}:print_format=summary",
            "-ar",
            "48000",  # Standard sample rate for video production
            temp_output,
        ]

        # Run FFmpeg for normalization
        logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg normalization failed: {result.stderr}")
            return False

        # Move the temp file to the output path
        if os.path.exists(temp_output):
            if input_path != output_path:
                # If output is different from input, just move the temp file
                os.rename(temp_output, output_path)
            else:
                # If overwriting the input, we need to replace it safely
                backup_path = f"{input_path}.bak"
                os.rename(input_path, backup_path)
                os.rename(temp_output, output_path)
                os.remove(backup_path)

            logger.debug(f"Audio normalized successfully: {output_path}")
            return True
        else:
            logger.error(f"Normalized output file not created: {temp_output}")
            return False

    except Exception as e:
        logger.exception(f"Error normalizing audio: {e}")
        return False


def normalize_final_mix(input_path: str, output_path: str) -> bool:
    """
    Apply broadcast-standard loudness normalization to a final audio mix.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file

    Returns:
        True if normalization was successful, False otherwise
    """
    # Use same parameters as individual tracks for consistency
    return normalize_audio_loudness(
        input_path,
        output_path,
        target_loudness=-16.0,
        true_peak=-1.5,
        loudness_range=11.0,
    )
