import logging
import os

from dotenv import load_dotenv

from youtube_uploader.config import YouTubeConfig
from youtube_uploader.token_manager import TokenManager
from youtube_uploader.uploader import YouTubeUploader

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(".env.test")


def test_youtube_auth():
    """Test YouTube authentication."""
    try:
        # Initialize token manager
        tm = TokenManager()

        # Get token status
        status = tm.get_token_status()
        logger.info("Token Status:")
        logger.info(f"Has Credentials: {status['has_credentials']}")
        logger.info(f"Last Refresh: {status['last_refresh']}")
        logger.info(f"Refresh Count: {status['refresh_count']}")
        logger.info(f"Last Error: {status['last_error']}")

        # Try to get YouTube service
        youtube = tm.get_youtube_service()
        if youtube:
            logger.info("Successfully authenticated with YouTube API")

            # Test channel access
            request = youtube.channels().list(part="snippet", mine=True)
            response = request.execute()

            if response["items"]:
                channel = response["items"][0]
                logger.info(
                    f"Successfully accessed channel: {channel['snippet']['title']}"
                )
                return True
            else:
                logger.error("No channels found")
                return False

        return False

    except Exception as e:
        logger.error(f"Authentication test failed: {str(e)}")
        return False


def test_upload_config():
    """Test YouTube upload configuration."""
    try:
        config = YouTubeConfig.from_env()
        logger.info("YouTube Configuration:")
        logger.info(f"Enabled: {config.enabled}")
        logger.info(f"Channel ID: {config.channel_id}")
        logger.info(f"Default Privacy: {config.default_privacy}")

        if not config.validate():
            logger.error("Configuration validation failed")
            return False

        return True

    except Exception as e:
        logger.error(f"Configuration test failed: {str(e)}")
        return False


if __name__ == "__main__":
    logger.info("Testing YouTube Authentication and Configuration...")

    # Test configuration
    if test_upload_config():
        logger.info("Configuration test passed")
    else:
        logger.error("Configuration test failed")
        exit(1)

    # Test authentication
    if test_youtube_auth():
        logger.info("Authentication test passed")
    else:
        logger.error("Authentication test failed")
        exit(1)

    logger.info("All tests passed successfully!")
