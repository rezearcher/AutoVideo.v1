import os
import json
import pickle
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
TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.files', 'token.pickle')
TOKEN_INFO_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.files', 'token_info.json')
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.files', 'client_secret.json')

class TokenManager:
    def __init__(self):
        self.credentials = None
        self.youtube = None
        self.token_info = self._load_token_info()

    def _load_token_info(self):
        """Load token information including last refresh time."""
        if os.path.exists(TOKEN_INFO_FILE):
            try:
                with open(TOKEN_INFO_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading token info: {e}")
        return {
            'last_refresh': None,
            'refresh_count': 0,
            'last_error': None
        }

    def _save_token_info(self):
        """Save token information."""
        try:
            with open(TOKEN_INFO_FILE, 'w') as f:
                json.dump(self.token_info, f)
        except Exception as e:
            logger.warning(f"Error saving token info: {e}")

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
            # Load existing token if available
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'rb') as token:
                    self.credentials = pickle.load(token)

            # Check if we need to refresh the token
            if self._should_refresh_token():
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    try:
                        self.credentials.refresh(Request())
                        self.token_info['refresh_count'] += 1
                        self.token_info['last_error'] = None
                    except RefreshError as e:
                        logger.warning(f"Token refresh failed: {e}")
                        self.token_info['last_error'] = str(e)
                        self.credentials = None
                else:
                    # In Cloud Run, we should use the pre-generated token
                    if os.path.exists(TOKEN_FILE):
                        with open(TOKEN_FILE, 'rb') as token:
                            self.credentials = pickle.load(token)
                            self.token_info['refresh_count'] = 1
                            self.token_info['last_error'] = None
                    else:
                        raise Exception("No token file found in .files directory")

                # Save the new token
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(self.credentials, token)
                
                self.token_info['last_refresh'] = datetime.now().isoformat()
                self._save_token_info()

            return self.credentials

        except Exception as e:
            logger.error(f"Error in get_credentials: {e}")
            self.token_info['last_error'] = str(e)
            self._save_token_info()
            raise

    def get_youtube_service(self):
        """Get YouTube API service instance."""
        if not self.youtube:
            credentials = self.get_credentials()
            self.youtube = build('youtube', 'v3', credentials=credentials)
        return self.youtube

    def clear_token(self):
        """Clear stored token and token info."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        if os.path.exists(TOKEN_INFO_FILE):
            os.remove(TOKEN_INFO_FILE)
        self.credentials = None
        self.youtube = None
        self.token_info = {
            'last_refresh': None,
            'refresh_count': 0,
            'last_error': None
        }
        self._save_token_info()

    def get_token_status(self):
        """Get current token status information."""
        return {
            'has_token': os.path.exists(TOKEN_FILE),
            'last_refresh': self.token_info['last_refresh'],
            'refresh_count': self.token_info['refresh_count'],
            'last_error': self.token_info['last_error']
        } 