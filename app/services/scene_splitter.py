import logging
import re
from typing import List

logger = logging.getLogger(__name__)


def split_into_scenes(
    story: str, max_scenes: int = 5, max_tokens_per_scene: int = 110
) -> List[str]:
    """
    Split a story into scenes for Veo video generation.

    Args:
        story (str): The story text to split
        max_scenes (int): Maximum number of scenes to generate
        max_tokens_per_scene (int): Maximum tokens per scene (roughly characters/4)

    Returns:
        List[str]: List of scene prompts ready for Veo
    """
    # Clean up the story
    clean_story = story.strip()

    # Split on paragraph breaks or double periods
    raw_splits = re.split(r"\n\n|\.\s+\.", clean_story)

    # Further split long paragraphs on sentence boundaries
    splits = []
    for paragraph in raw_splits:
        if len(paragraph) > max_tokens_per_scene * 4:  # Approximate token count
            # Split on sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= max_tokens_per_scene * 4:
                    current_chunk += (" " if current_chunk else "") + sentence
                else:
                    if current_chunk:
                        splits.append(current_chunk)
                    current_chunk = sentence

            if current_chunk:
                splits.append(current_chunk)
        else:
            splits.append(paragraph)

    # Limit to max_scenes
    if len(splits) > max_scenes:
        # Take evenly distributed scenes
        step = len(splits) / max_scenes
        scenes = [splits[int(i * step)] for i in range(max_scenes)]
    else:
        scenes = splits[:max_scenes]

    # If we don't have enough scenes, duplicate the last one
    while len(scenes) < max_scenes:
        scenes.append(scenes[-1])

    # Format each scene for Veo
    formatted_scenes = []
    for i, scene_text in enumerate(scenes):
        # Add cinematic elements to enhance the prompt
        veo_prompt = f"""
        A cinematic {8 if i < max_scenes-1 else 5}-second shot of {scene_text}.
        Camera: {['tracking shot', 'medium close-up', 'slow dolly-in', 'gentle pan', 'static wide shot'][i % 5]}.
        Lighting: {['natural daylight', 'warm sunset glow', 'cool blue evening', 'dramatic side lighting', 'soft diffused light'][i % 5]}.
        Style: cinematic 4K, high quality, detailed.
        """.strip()

        formatted_scenes.append(veo_prompt)

    logger.info(f"Split story into {len(formatted_scenes)} scenes")
    return formatted_scenes
