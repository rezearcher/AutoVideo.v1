import json
import os
import pickle
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CREDENTIALS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".files", "client_secret.json"
)
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".files", "token.pickle"
)


def main():
    """Generate a YouTube token file."""
    try:
        # Check if credentials file exists
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"Error: {CREDENTIALS_FILE} not found")
            return False

        # Create .files directory if it doesn't exist
        os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)

        # Run the OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        credentials = flow.run_local_server(port=0)

        # Save the token
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(credentials, token)

        print(f"Token saved to {TOKEN_FILE}")
        return True

    except Exception as e:
        print(f"Error generating token: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
