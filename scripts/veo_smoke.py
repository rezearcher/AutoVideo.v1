#!/usr/bin/env python3
import os
import sys
import uuid

import vertexai
from vertexai.preview.generative_models import GenerativeModel


def main():
    project_id = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    if not project_id:
        print("❌ No project ID provided. Pass as argument or set GOOGLE_CLOUD_PROJECT")
        sys.exit(1)

    print(f"🔍 Testing Veo API with project {project_id}...")

    # Initialize Vertex AI
    vertexai.init(project=project_id, location="us-central1")

    try:
        # Load the Veo model
        print("📋 Loading Veo model...")
        model = GenerativeModel("veo-3.0-generate-preview")

        # Generate a short test video
        print("🎬 Generating test video...")
        op = model.generate_video_async(
            "Simple white cat sitting on a keyboard",
            generation_config={
                "durationSeconds": 5,
                "aspectRatio": "16:9",
                "sampleCount": 1,
            },
        )

        print("⏳ Waiting for operation to complete (may take a few minutes)...")
        resp = op.result(timeout=300)

        if resp and resp.videos and len(resp.videos) > 0:
            print(f"✅ Veo smoke test passed! Video URI: {resp.videos[0].gcs_uri}")
            return True
        else:
            print("❌ Veo response did not contain any videos")
            sys.exit(1)
    except Exception as e:
        error_str = str(e).lower()
        if (
            "quota" in error_str
            or "resource exhausted" in error_str
            or "insufficient_tokens" in error_str
        ):
            print(f"❌ Veo quota exceeded or insufficient tokens: {e}")
            print("💡 Please check your Veo API quota in Google Cloud Console")
            sys.exit(2)  # Special exit code for quota issues
        elif "permission" in error_str or "unauthorized" in error_str:
            print(f"❌ Permission denied accessing Veo API: {e}")
            print("💡 Check service account permissions and API enablement")
            sys.exit(3)  # Special exit code for permission issues
        else:
            print(f"❌ Veo smoke test failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Veo smoke test failed with unexpected error: {e}")
        sys.exit(1)
