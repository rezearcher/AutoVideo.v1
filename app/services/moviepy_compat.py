"""
Compatibility module for MoviePy.
This stub indicates that MoviePy is not available and should be used instead of direct imports.
"""

import logging

logger = logging.getLogger(__name__)

# Set MoviePy as unavailable
MOVIEPY_AVAILABLE = False


# Define dummy classes to prevent import errors elsewhere
class DummyClip:
    def __init__(self, *args, **kwargs):
        raise ImportError("MoviePy is not available")

    def set_duration(self, *args, **kwargs):
        pass

    def set_audio(self, *args, **kwargs):
        pass

    def write_videofile(self, *args, **kwargs):
        pass


# Define all the dummy imports needed by other modules
AudioFileClip = ImageClip = VideoFileClip = CompositeVideoClip = TextClip = DummyClip
concatenate_videoclips = lambda clips: DummyClip()
resize = lambda clip, width=None: clip

logger.info("Using MoviePy stub - MoviePy functionality is disabled")
