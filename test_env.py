import os
from dotenv import load_dotenv


def test_env_vars():
    """Test if all required environment variables are set"""
    load_dotenv()

    required_vars = [
        "OPENAI_API_KEY",
        "OPENAI_ORG_ID",
        "ELEVENLABS_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_PROJECT_ID",
    ]

    optional_vars = ["PEXELS_API_KEY", "DID_API_KEY", "ELAI_API_KEY"]

    print("\nChecking required environment variables:")
    all_required_set = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var} is set")
        else:
            print(f"✗ {var} is not set")
            all_required_set = False

    print("\nChecking optional environment variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var} is set")
        else:
            print(f"! {var} is not set (optional)")

    return all_required_set


if __name__ == "__main__":
    if test_env_vars():
        print(
            "\nAll required environment variables are set! You can proceed with running the main application."
        )
    else:
        print(
            "\nSome required environment variables are missing. Please set them before running the main application."
        )
