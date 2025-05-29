import logging
import os
import shutil
from datetime import datetime


class OutputManager:
    def __init__(self, base_dir="output"):
        """
        Initialize the OutputManager.

        Args:
            base_dir (str): Base directory for all outputs
        """
        self.base_dir = base_dir
        self.current_run_dir = None
        self.subdirs = {}

        # Create base directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)

        # Set up logging after ensuring base directory exists
        self.setup_logging()

    def setup_logging(self):
        """Set up logging configuration with a dedicated logs directory."""
        logs_dir = os.path.join(self.base_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # Configure logging
        log_file = os.path.join(
            logs_dir, f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )

    def create_run_directory(self):
        """
        Create a new directory for the current run with subdirectories.

        Returns:
            str: Path to the created directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_run_dir = os.path.join(self.base_dir, f"run_{timestamp}")
        os.makedirs(self.current_run_dir, exist_ok=True)

        # Create subdirectories
        self.subdirs = {
            "images": os.path.join(self.current_run_dir, "images"),
            "audio": os.path.join(self.current_run_dir, "audio"),
            "video": os.path.join(self.current_run_dir, "video"),
            "text": os.path.join(self.current_run_dir, "text"),
        }

        # Create all subdirectories
        for subdir in self.subdirs.values():
            os.makedirs(subdir, exist_ok=True)

        return self.current_run_dir

    def get_path(self, filename, subdir=None):
        """
        Get the full path for a file in the current run directory.

        Args:
            filename (str): Name of the file
            subdir (str, optional): Subdirectory to place the file in

        Returns:
            str: Full path to the file
        """
        if not self.current_run_dir:
            raise ValueError(
                "No run directory created yet. Call create_run_directory() first."
            )

        if subdir and subdir in self.subdirs:
            return os.path.join(self.subdirs[subdir], filename)
        return os.path.join(self.current_run_dir, filename)

    def save_text(self, content: str, filepath: str, subdir: str = "text") -> str:
        """Save text content to a file in the specified subdirectory.

        Args:
            content: The text content to save
            filepath: The name of the file to save
            subdir: The subdirectory to save in (default: 'text')

        Returns:
            str: The path where the file was saved
        """
        if not os.path.isabs(filepath):
            filepath = self.get_path(os.path.basename(filepath), subdir)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def save_binary(self, content, filename, subdir=None):
        """
        Save binary content to a file.

        Args:
            content (bytes): Binary content to save
            filename (str): Name of the file
            subdir (str, optional): Subdirectory to save the file in

        Returns:
            str: Path to the saved file
        """
        filepath = self.get_path(filename, subdir)
        with open(filepath, "wb") as f:
            f.write(content)
        return filepath

    def cleanup(self):
        """
        Clean up temporary files in the current run directory.
        """
        if self.current_run_dir and os.path.exists(self.current_run_dir):
            for filename in os.listdir(self.current_run_dir):
                if filename.startswith("temp_"):
                    os.remove(os.path.join(self.current_run_dir, filename))

    def ensure_dir_exists(self, directory):
        """
        Ensure that a directory exists, creating it if necessary.

        Args:
            directory (str): Path to the directory
        """
        os.makedirs(directory, exist_ok=True)


def create_output_directory():
    """
    Creates a structured output directory for the video generation process.
    Returns a dictionary with paths to various output directories.
    """
    # Create base output directory if it doesn't exist
    base_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(base_dir, exist_ok=True)

    # Create timestamp-based directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(base_dir, timestamp)
    os.makedirs(output_dir, exist_ok=True)

    # Create subdirectories for different types of files
    subdirs = {
        "images": os.path.join(output_dir, "images"),
        "audio": os.path.join(output_dir, "audio"),
        "video": os.path.join(output_dir, "video"),
        "text": os.path.join(output_dir, "text"),
    }

    # Create all subdirectories
    for subdir in subdirs.values():
        os.makedirs(subdir, exist_ok=True)

    return {
        "base": base_dir,
        "timestamp": timestamp,
        "output": output_dir,
        **subdirs,
    }


def get_output_paths(dirs, timestamp):
    """
    Returns a dictionary of output file paths for the current video generation.

    Args:
        dirs (dict): Dictionary of directory paths from create_output_directory()
        timestamp (str): Timestamp string for unique file naming

    Returns:
        dict: Dictionary of output file paths
    """
    return {
        "story": os.path.join(dirs["text"], f"story_{timestamp}.txt"),
        "voiceover": os.path.join(dirs["audio"], f"voiceover_{timestamp}.mp3"),
        "video": os.path.join(dirs["video"], f"output_video_{timestamp}.mp4"),
        "video_with_captions": os.path.join(
            dirs["video"], f"video_with_captions_{timestamp}.mp4"
        ),
        "image_template": os.path.join(dirs["images"], f"image_{timestamp}_{{}}.png"),
    }
