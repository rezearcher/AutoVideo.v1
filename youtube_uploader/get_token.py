import os
import sys
import logging
from token_manager import TokenManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run the token authorization flow."""
    try:
        token_manager = TokenManager()

        # Check current token status
        status = token_manager.get_token_status()
        if status["has_token"]:
            logger.info("Existing token found.")
            logger.info(f"Last refresh: {status['last_refresh']}")
            logger.info(f"Refresh count: {status['refresh_count']}")
            if status["last_error"]:
                logger.warning(f"Last error: {status['last_error']}")

        # This will trigger the OAuth flow if needed
        credentials = token_manager.get_credentials()

        if credentials and credentials.valid:
            logger.info("Successfully obtained and stored credentials!")
            logger.info(
                "You can now use the YouTube uploader without manual authentication."
            )

            # Show new token status
            status = token_manager.get_token_status()
            logger.info(f"Token will be valid until: {status['last_refresh']}")
            return True
        else:
            logger.error("Failed to obtain valid credentials.")
            return False

    except Exception as e:
        logger.error(f"Error during token authorization: {str(e)}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
