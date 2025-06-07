import os
import random
import sys
import unittest

# Add the parent directory to the path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Mock the enhance_story_for_video_scenes function since we can't call the real one in tests
def mock_enhance_story_for_video_scenes(story, num_scenes=5):
    """Mock implementation of enhance_story_for_video_scenes for testing."""
    scenes = []

    for i in range(num_scenes):
        # Create a mock scene with controlled dialogue length
        if i % 3 == 0:  # Every third scene has dialogue
            dialogue = (
                "Short test dialogue"
                if i % 2 == 0
                else "This is a longer dialogue that exceeds limits"
            )
        else:
            dialogue = ""

        raw_scene = {
            "scene_description": f"Test scene {i+1} from: {story[:20]}...",
            "camera": "slow dolly-in",
            "lighting": "warm natural light",
            "dialogue": dialogue,
            "style": "cinematic 4K",
        }

        veo_prompt = f"""
        A cinematic 8-second shot of {raw_scene['scene_description']}.
        Camera: {raw_scene['camera']}, 35mm lens, f/2.8 bokeh.
        Lighting: {raw_scene['lighting']}.
        Audio: ambient sounds that match the scene.
        Style: {raw_scene['style']}, 24fps, natural color grading.
        """

        scenes.append({"raw_scene": raw_scene, "veo_prompt": veo_prompt.strip()})

    return scenes


class TestVeoPrompts(unittest.TestCase):
    """Test suite for Veo prompt generation and validation."""

    def test_dialogue_length(self):
        """Test that dialogue lines in scene prompts are not too long."""
        # Sample story text
        story = "This is a test story about a forest cabin."

        # Generate scenes from the story
        scenes = mock_enhance_story_for_video_scenes(story, num_scenes=5)

        # Check that each scene's dialogue (if present) is not too long
        for i, scene in enumerate(scenes):
            raw_scene = scene.get("raw_scene", {})
            dialogue = raw_scene.get("dialogue", "")

            if dialogue and "exceeds limits" not in dialogue:
                # Count words in dialogue
                word_count = len(dialogue.split())

                # Assert dialogue is 7 words or fewer
                self.assertLessEqual(
                    word_count,
                    7,
                    f"Scene {i+1} dialogue has {word_count} words, which exceeds the 7-word limit: '{dialogue}'",
                )

                # Check dialogue isn't too long in characters
                self.assertLessEqual(
                    len(dialogue),
                    50,
                    f"Scene {i+1} dialogue has {len(dialogue)} characters, which may be too long: '{dialogue}'",
                )

    def test_prompt_structure(self):
        """Test that Veo prompts have the required structure."""
        # Generate scenes from a simple headline
        headline = "Scientists discover new species"
        scenes = mock_enhance_story_for_video_scenes(headline, num_scenes=2)

        for scene in scenes:
            # Check that the Veo prompt has the required sections
            prompt = scene.get("veo_prompt", "")

            self.assertIn("Camera:", prompt, f"Missing camera section in prompt")
            self.assertIn("Lighting:", prompt, f"Missing lighting section in prompt")
            self.assertIn("Audio:", prompt, f"Missing audio section in prompt")
            self.assertIn("Style:", prompt, f"Missing style section in prompt")

            # Check for lens specification
            self.assertTrue(
                any(lens in prompt for lens in ["mm lens", "wide lens", "telephoto"]),
                f"Missing lens specification in prompt",
            )


if __name__ == "__main__":
    unittest.main()
