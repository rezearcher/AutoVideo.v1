import os
import sys
import base64
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.files', 'token.pickle')

def main():
    """Prepare YouTube token for GitHub Secrets."""
    try:
        # Check if token file exists
        if not os.path.exists(TOKEN_FILE):
            print(f"Error: {TOKEN_FILE} not found")
            print("Please run generate_youtube_token.py first")
            return False

        # Read and encode token file
        with open(TOKEN_FILE, 'rb') as f:
            token_data = f.read()
            encoded = base64.b64encode(token_data).decode('utf-8')

        print("\nAdd this as a GitHub Secret named YOUTUBE_TOKEN:\n")
        print(encoded)
        print("\nYou can do this by:")
        print("1. Go to your GitHub repository")
        print("2. Click Settings > Secrets and variables > Actions")
        print("3. Click 'New repository secret'")
        print("4. Name: YOUTUBE_TOKEN")
        print("5. Value: (paste the encoded string above)")
        print("6. Click 'Add secret'")

        return True

    except Exception as e:
        print(f"Error preparing token: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 