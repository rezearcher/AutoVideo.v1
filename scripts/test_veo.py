#!/usr/bin/env python3
"""
Test script for Veo video generation.
Uses the veo_adapter module to create a simple test video.

Usage:
    python scripts/test_veo.py [--story "Your custom story"]
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_veo_generation(story=None):
    """
    Test Veo video generation with a sample story or provided story.

    Args:
        story (str, optional): Custom story to use. If None, a default story is used.
    """
    # Default test story
    if story is None:
        story = """
        A robot discovers an ancient library filled with books about human emotions.
        As it reads, it begins to understand what it means to feel.
        Gradually, the robot develops its own emotions, starting with curiosity, then wonder.
        By the end of its journey, the robot experiences the most human emotion of all: hope.
        """

    print(f"Testing Veo video generation with story:\n{story}\n")

    # Prepare output directory
    output_dir = Path("output/test_veo")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Import the necessary modules
        from app.services.scene_splitter import split_into_scenes
        from app.services.veo_adapter import make_clip

        # Split the story into scenes
        print("Splitting story into scenes...")
        scene_prompts = split_into_scenes(story, max_scenes=2)

        # Generate videos for each scene
        video_paths = []
        for i, prompt in enumerate(scene_prompts):
            print(f"\nScene {i+1}/{len(scene_prompts)}:")
            print(f"Prompt: {prompt[:150]}...")

            start_time = time.time()

            # Generate the video
            print(f"Generating video for scene {i+1}...")
            video_path = make_clip(
                prompt, seconds=8 if i < len(scene_prompts) - 1 else 5
            )

            # Move to output directory
            dest_path = output_dir / f"scene_{i+1}.mp4"
            if os.path.exists(video_path):
                os.rename(video_path, dest_path)
                video_paths.append(str(dest_path))
                print(f"Video saved to {dest_path}")
                print(f"Generation took {time.time() - start_time:.2f} seconds")
            else:
                print(f"Warning: Video file not found at {video_path}")

        # Display results
        if video_paths:
            print(f"\nSuccessfully generated {len(video_paths)} video clips:")
            for path in video_paths:
                print(f"- {path}")
            print("\nTest completed successfully!")
        else:
            print("\nNo videos were generated. Check the logs for errors.")

    except ImportError as e:
        print(f"Error: Could not import required modules: {e}")
        print("Make sure you have installed the required dependencies.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during video generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Veo video generation")
    parser.add_argument("--story", type=str, help="Custom story to use for the test")
    args = parser.parse_args()

    test_veo_generation(args.story)
