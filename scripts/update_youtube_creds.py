"""
Script to update YouTube credentials in .env file from a JSON file in downloads.
"""

import os
import json
import shutil
from pathlib import Path
from dotenv import load_dotenv, set_key


def get_downloads_path():
    """Get the path to the downloads folder."""
    return str(Path.home() / "Downloads")


def find_credentials_file():
    """Find the YouTube credentials JSON file in downloads."""
    downloads_path = get_downloads_path()
    # Look for files that might contain YouTube credentials
    possible_files = [
        "client_secret.json",
        "youtube_credentials.json",
        "oauth2_credentials.json",
    ]

    for file in possible_files:
        file_path = os.path.join(downloads_path, file)
        if os.path.exists(file_path):
            return file_path
    return None


def update_env_file(credentials):
    """Update .env file with YouTube credentials."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    # Load existing .env file
    load_dotenv(env_path)

    # Update YouTube credentials
    if "installed" in credentials:
        # Format from Google Cloud Console
        set_key(env_path, "YOUTUBE_CLIENT_ID", credentials["installed"]["client_id"])
        set_key(
            env_path, "YOUTUBE_CLIENT_SECRET", credentials["installed"]["client_secret"]
        )
    else:
        # Custom format
        set_key(env_path, "YOUTUBE_CLIENT_ID", credentials.get("client_id", ""))
        set_key(env_path, "YOUTUBE_CLIENT_SECRET", credentials.get("client_secret", ""))

    print("Updated .env file with YouTube credentials")


def main():
    # Find credentials file
    creds_file = find_credentials_file()
    if not creds_file:
        print("No credentials file found in Downloads folder.")
        print(
            "Please make sure you have downloaded the credentials file from Google Cloud Console."
        )
        return

    try:
        # Read credentials
        with open(creds_file, "r") as f:
            credentials = json.load(f)

        # Update .env file
        update_env_file(credentials)

        # Create backup of credentials file
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, "youtube_credentials_backup.json")
        shutil.copy2(creds_file, backup_path)
        print(f"Created backup of credentials at: {backup_path}")

        # Ask if user wants to delete the original file
        response = input(
            "Would you like to delete the credentials file from Downloads? (y/N): "
        )
        if response.lower() == "y":
            os.remove(creds_file)
            print("Deleted credentials file from Downloads")

    except json.JSONDecodeError:
        print("Error: Invalid JSON file")
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
