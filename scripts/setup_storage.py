#!/usr/bin/env python3
"""
Setup Google Cloud Storage buckets with proper structure and lifecycle rules.
This script will:
1. Create the bucket if it doesn't exist
2. Create the folder structure
3. Set lifecycle rules to auto-delete temporary files
"""

import argparse
import os
import sys
from typing import Any, Dict, List

from google.cloud import storage
from google.cloud.exceptions import Conflict

# Add the project root to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.config.storage import BUCKET_PATHS, get_storage_path


def create_bucket_if_not_exists(
    bucket_name: str, location: str = "us-central1"
) -> storage.Bucket:
    """Create a new bucket if it doesn't already exist."""
    client = storage.Client()

    try:
        bucket = client.get_bucket(bucket_name)
        print(f"✅ Bucket {bucket_name} already exists")
    except Exception:
        try:
            bucket = client.create_bucket(bucket_name, location=location)
            print(f"✅ Created bucket {bucket_name} in {location}")
        except Conflict:
            bucket = client.get_bucket(bucket_name)
            print(f"✅ Bucket {bucket_name} already exists (race condition)")

    return bucket


def create_folder_structure(bucket: storage.Bucket, paths: Dict) -> None:
    """Create the folder structure in the bucket."""

    def _create_folders(path_dict, prefix=""):
        for key, value in path_dict.items():
            if isinstance(value, dict):
                _create_folders(value, f"{prefix}{key}/")
            else:
                folder_path = f"{prefix}{value}/"
                blob = bucket.blob(folder_path)
                if not blob.exists():
                    blob.upload_from_string("")
                    print(f"📁 Created folder: {folder_path}")

    _create_folders(paths)
    print(f"✅ Folder structure created")


def setup_lifecycle_rules(bucket: storage.Bucket) -> None:
    """Set up lifecycle rules for the bucket."""
    # Define lifecycle rules
    lifecycle_rules = [
        # Rule 1: Delete objects in temp/ directory after 24 hours
        {
            "action": {"type": "Delete"},
            "condition": {
                "age": 1,  # 1 day
                "matchesPrefix": ["temp/"],
            },
        },
        # Rule 2: Delete objects in videos/clips/ directory after 1 day
        {
            "action": {"type": "Delete"},
            "condition": {
                "age": 1,  # 1 day
                "matchesPrefix": ["videos/clips/"],
            },
        },
        # Rule 3: Delete cache files after 7 days to prevent stale cache
        {
            "action": {"type": "Delete"},
            "condition": {
                "age": 7,  # 7 days
                "matchesPrefix": ["videos/cache/"],
            },
        },
    ]

    # Apply lifecycle rules
    bucket.lifecycle_rules = lifecycle_rules
    bucket.update()
    print(f"✅ Lifecycle rules applied: {len(lifecycle_rules)} rules")
    print(f"   - Temporary files (temp/*) deleted after 1 day")
    print(f"   - Video clips (videos/clips/*) deleted after 1 day")
    print(f"   - Cache files (videos/cache/*) deleted after 7 days")


def main():
    parser = argparse.ArgumentParser(
        description="Setup GCS bucket structure and lifecycle rules"
    )
    parser.add_argument("--bucket", help="Bucket name (default from settings)")
    parser.add_argument("--location", default="us-central1", help="Bucket location")
    args = parser.parse_args()

    bucket_name = args.bucket or settings.GCS_BUCKET_NAME
    if not bucket_name:
        print(
            "❌ Error: No bucket name provided. Use --bucket or set GCS_BUCKET_NAME in settings."
        )
        sys.exit(1)

    print(f"🪣 Setting up bucket structure for: {bucket_name}")

    # Create or get the bucket
    bucket = create_bucket_if_not_exists(bucket_name, args.location)

    # Create folder structure
    create_folder_structure(bucket, BUCKET_PATHS)

    # Set lifecycle rules
    setup_lifecycle_rules(bucket)

    print("✅ Bucket setup complete!")


if __name__ == "__main__":
    main()
