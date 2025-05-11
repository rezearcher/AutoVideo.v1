import os
import json
import logging
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class TokenManager:
    def __init__(self):
        self.credentials = None
        self.youtube = None
        self.token_info = {
            'last_refresh': None,
            'refresh_count': 0,
            'last_error': None
        }

    def _should_refresh_token(self):
        """Determine if token should be refreshed based on Google's guidelines."""
        if not self.token_info['last_refresh']:
            return True

        last_refresh = datetime.fromisoformat(self.token_info['last_refresh'])
        now = datetime.now()

        # Refresh if:
        # 1. Token is older than 6 hours (Google's recommended refresh interval)
        # 2. We've had a refresh error
        # 3. We've exceeded 50 refreshes in 24 hours (Google's limit)
        if (now - last_refresh) > timedelta(hours=6):
            return True
        if self.token_info['last_error']:
            return True
        if self.token_info['refresh_count'] >= 50 and (now - last_refresh) < timedelta(hours=24):
            return True

        return False

    def get_credentials(self):
        """Get valid credentials for YouTube API."""
        try:
            # Get credentials from environment variables
            client_id = os.getenv('YOUTUBE_CLIENT_ID')
            client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
            project_id = os.getenv('YOUTUBE_PROJECT_ID')

            if not all([client_id, client_secret, project_id]):
                raise ValueError("Missing required YouTube credentials in environment variables")

            # Create credentials object from environment variables
            self.credentials = Credentials(
                None,  # No token initially
                refresh_token=None,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )

            # Check if we need to refresh the token
            if self._should_refresh_token():
                try:
                    self.credentials.refresh(Request())
                    self.token_info['refresh_count'] += 1
                    self.token_info['last_error'] = None
                except RefreshError as e:
                    logger.warning(f"Token refresh failed: {e}")
                    self.token_info['last_error'] = str(e)
                    self.credentials = None
                    raise

                self.token_info['last_refresh'] = datetime.now().isoformat()

            return self.credentials

        except Exception as e:
            logger.error(f"Error in get_credentials: {e}")
            self.token_info['last_error'] = str(e)
            raise

    def get_youtube_service(self):
        """Get YouTube API service instance."""
        if not self.youtube:
            credentials = self.get_credentials()
            self.youtube = build('youtube', 'v3', credentials=credentials)
        return self.youtube

    def get_token_status(self):
        """Get current token status information."""
        return {
            'has_credentials': bool(self.credentials),
            'last_refresh': self.token_info['last_refresh'],
            'refresh_count': self.token_info['refresh_count'],
            'last_error': self.token_info['last_error']
        } 