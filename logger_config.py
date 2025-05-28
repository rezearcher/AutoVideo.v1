import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def setup_logger(name, log_file=None, level=None):
    """
    Set up a logger with the specified name and configuration.

    Args:
        name (str): Name of the logger
        log_file (str, optional): Path to the log file. If None, uses the LOG_FILE from .env
        level (str, optional): Logging level. If None, uses the LOG_LEVEL from .env

    Returns:
        logging.Logger: Configured logger instance
    """
    # Get configuration from environment variables
    log_file = log_file or os.getenv("LOG_FILE", "video_generation.log")
    log_level = level or os.getenv("LOG_LEVEL", "INFO")

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Create formatters
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")

    # Create and configure file handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Create and configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


# Create default logger
logger = setup_logger("autovideo")
