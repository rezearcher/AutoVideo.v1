#!/usr/bin/env python3
import os
import random
import sys
import time
import uuid

import vertexai
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel


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

    # Retry parameters
    max_retries = 3
    retry_count = 0
    base_delay = 5  # seconds

    while retry_count <= max_retries:
        try:
            # Load the Veo model
            if retry_count == 0:
                print("📋 Loading Veo model...")
            else:
                print(
                    f"📋 Retry attempt {retry_count}/{max_retries} after quota limit..."
                )

            model = GenerativeModel("veo-3.0-generate-preview")

            # Generate a short test video
            print("🎬 Generating test video...")

            # Use the correct method for video generation with simpler parameters
            response = model.generate_content(
                "Generate a 5-second video of a simple white cat sitting on a keyboard. HD quality.",
                # Generation config without nested video object
                generation_config=GenerationConfig(
                    temperature=0.4,
                    top_p=1.0,
                    top_k=32,
                    candidate_count=1,
                    max_output_tokens=2048,
                ),
            )

            print("⏳ Checking response...")

            # Check if we have a video in the response
            if response and hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "content") and candidate.content:
                    video_part = None
                    for part in candidate.content.parts:
                        if hasattr(part, "video"):
                            video_part = part.video
                            break

                    if video_part:
                        print(f"✅ Veo smoke test passed! Video generated successfully")
                        return True

            print("❌ Veo response did not contain any videos")
            sys.exit(1)
        except Exception as e:
            error_str = str(e).lower()

            # Check for quota/rate limit errors
            if (
                "quota" in error_str
                or "resource exhausted" in error_str
                or "insufficient_tokens" in error_str
                or "429" in error_str
            ):
                retry_count += 1

                if retry_count <= max_retries:
                    # Calculate exponential backoff with jitter
                    delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                    print(f"⏱️ Quota limit hit. Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    print(f"❌ Veo quota exceeded or insufficient tokens: {e}")
                    print("💡 Please check your Veo API quota in Google Cloud Console")
                    print(
                        "💡 Consider requesting a quota increase: https://cloud.google.com/vertex-ai/docs/generative-ai/quotas-genai"
                    )
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
