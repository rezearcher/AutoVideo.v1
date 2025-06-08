"""
Compatibility module for MoviePy imports.
This handles differences between MoviePy 0.x and 2.x versions.
"""

import logging

logger = logging.getLogger(__name__)

# Try to import using the new package structure (MoviePy 2.0+)
try:
    import moviepy.editor.editor as editor
    from moviepy.editor.editor import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    from moviepy.editor.video.fx.all import resize

    logger.info("Using MoviePy 2.0+ import paths")
    MOVIEPY_AVAILABLE = True
except ImportError:
    # Fall back to old import paths (MoviePy 0.x)
    try:
        from moviepy.editor import (
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
            TextClip,
            VideoFileClip,
            concatenate_videoclips,
        )
        from moviepy.video.fx.all import resize

        logger.info("Using MoviePy 0.x import paths")
        MOVIEPY_AVAILABLE = True
    except ImportError:
        logger.error("Failed to import MoviePy. Video features will be unavailable.")
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

        AudioFileClip = ImageClip = VideoFileClip = CompositeVideoClip = TextClip = (
            DummyClip
        )
        concatenate_videoclips = lambda clips: DummyClip()
        resize = lambda clip, width=None: clip
