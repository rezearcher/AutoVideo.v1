import os
import sys

# Add the parent directory to the path so we can import the app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.scene_splitter import split_into_scenes


def test_split_into_scenes_basic():
    """Test basic functionality of split_into_scenes with a simple story."""
    # Simple test story
    story = """
    Once upon a time, there was a robot who dreamed of becoming human.
    
    Every day, the robot would study human behavior and try to mimic it.
    
    One day, the robot met a kind scientist who offered to help.
    
    The scientist worked tirelessly to give the robot more human-like qualities.
    
    Finally, the robot realized that being human isn't about appearance, but about compassion and understanding.
    """

    # Split into scenes
    scenes = split_into_scenes(story, max_scenes=5)

    # Basic assertions
    assert scenes is not None
    assert len(scenes) == 5
    assert all(isinstance(scene, str) for scene in scenes)

    # Check that each scene contains camera and lighting information
    camera_terms = [
        "tracking shot",
        "medium close-up",
        "slow dolly-in",
        "gentle pan",
        "static wide shot",
    ]
    lighting_terms = [
        "natural daylight",
        "warm sunset glow",
        "cool blue evening",
        "dramatic side lighting",
        "soft diffused light",
    ]

    for i, scene in enumerate(scenes):
        assert "cinematic" in scene.lower()
        assert camera_terms[i % 5] in scene
        assert lighting_terms[i % 5] in scene

    print("✓ test_split_into_scenes_basic passed")


def test_split_into_scenes_long_text():
    """Test that the function properly handles very long text."""
    # Create a long story by repeating paragraphs
    paragraph = (
        "This is a test paragraph with enough text to ensure we have a substantial amount of content. "
        * 20
    )
    long_story = "\n\n".join([paragraph] * 10)  # 10 paragraphs

    # Split into different numbers of scenes
    scenes_3 = split_into_scenes(long_story, max_scenes=3)
    scenes_5 = split_into_scenes(long_story, max_scenes=5)
    scenes_8 = split_into_scenes(long_story, max_scenes=8)

    # Check counts
    assert len(scenes_3) == 3
    assert len(scenes_5) == 5
    assert len(scenes_8) == 8

    # Check that the scenes are different
    assert scenes_3[0] != scenes_3[1]
    assert len(set(scenes_5)) == 5  # All scenes should be unique

    print("✓ test_split_into_scenes_long_text passed")


def test_split_into_scenes_empty_input():
    """Test behavior with empty input."""
    # Empty string
    scenes = split_into_scenes("", max_scenes=5)

    # Should still return the requested number of scenes
    assert len(scenes) == 5

    # Check that all scenes are valid strings
    assert all(isinstance(scene, str) for scene in scenes)
    assert all(len(scene) > 0 for scene in scenes)

    # Don't test for identical scenes as the function might add random variations

    print("✓ test_split_into_scenes_empty_input passed")


def test_split_into_scenes_formatting():
    """Test that the output scenes are properly formatted for Veo."""
    story = "A simple test story about a character who goes on an adventure."

    scenes = split_into_scenes(story, max_scenes=1)
    assert len(scenes) == 1

    scene = scenes[0]

    # Check for formatting elements
    assert "cinematic" in scene
    assert "Camera:" in scene
    assert "Lighting:" in scene
    assert "Style:" in scene

    # Verify it includes the story content
    assert "adventure" in scene

    print("✓ test_split_into_scenes_formatting passed")


if __name__ == "__main__":
    # Run the tests manually
    print("Running tests...")
    test_split_into_scenes_basic()
    test_split_into_scenes_long_text()
    test_split_into_scenes_empty_input()
    test_split_into_scenes_formatting()
    print("All tests passed!")
