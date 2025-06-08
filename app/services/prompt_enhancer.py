"""Service for enhancing video generation prompts using Gemini."""

import logging
import os
from typing import Any, Dict, List, Optional, Union

try:
    import vertexai
    from vertexai.preview.generative_models import (
        GenerationConfig,
        GenerativeModel,
        Part,
    )

    VERTEXAI_AVAILABLE = True
except ImportError:
    logging.warning("Vertexai Gemini package not available")
    VERTEXAI_AVAILABLE = False

from app.config import settings

logger = logging.getLogger(__name__)


class PromptEnhancerService:
    """Service for enhancing video generation prompts using Gemini."""

    def __init__(self):
        self._gemini_enabled = settings.GEMINI_ENABLED
        self._initialized = False
        self._model = None

        if self._gemini_enabled and VERTEXAI_AVAILABLE:
            self._initialize()
        else:
            if not self._gemini_enabled:
                logger.info("Gemini prompt enhancement disabled by configuration")
            if not VERTEXAI_AVAILABLE:
                logger.warning(
                    "Gemini prompt enhancement not available: Vertex AI package not installed"
                )

    def _initialize(self):
        """Initialize the Gemini model."""
        try:
            vertexai.init(project=settings.GCP_PROJECT, location="us-central1")
            self._model = GenerativeModel("gemini-2.5-pro-vision")
            self._initialized = True
            logger.info("Gemini model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if Gemini prompt enhancement is available."""
        return self._gemini_enabled and self._initialized and VERTEXAI_AVAILABLE

    def enhance_video_prompt(
        self,
        base_prompt: str,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        reference_image_path: Optional[str] = None,
    ) -> str:
        """
        Enhance a basic video prompt with cinematic details using Gemini.

        Args:
            base_prompt: Basic text description of the desired video
            duration_seconds: Desired video duration in seconds
            aspect_ratio: Desired aspect ratio
            reference_image_path: Optional path to a reference image

        Returns:
            Enhanced prompt with cinematic details
        """
        if not self.is_available():
            # Fall back to simple enhancement if Gemini isn't available
            return self._simple_enhance_prompt(
                base_prompt, duration_seconds, aspect_ratio
            )

        try:
            # Prepare the system prompt
            system_prompt = (
                "You are a professional cinematographer. Your task is to enhance video prompts "
                "with cinematic camera movement, lighting, and scene direction details. "
                "Don't change the main subject of the prompt, just add detail that will help "
                "an AI video generator create higher quality, more cinematic output."
            )

            # Prepare content parts
            content_parts = []

            # Add reference image if provided
            if reference_image_path and os.path.exists(reference_image_path):
                try:
                    content_parts.append(
                        Part.from_uri(reference_image_path, mime_type="image/jpeg")
                    )
                    logger.info(
                        f"Added reference image to prompt: {reference_image_path}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to add reference image to prompt: {e}")

            # Prepare the user prompt
            user_prompt = (
                f"Enhance the following basic prompt for a {duration_seconds}-second video in {aspect_ratio} aspect ratio:\n\n"
                f'"{base_prompt}"\n\n'
                f"Add cinematic details like camera movements (pan, dolly, zoom), lighting conditions, "
                f"time of day, atmosphere, color palette suggestions, and scene composition. "
                f"Keep your enhanced prompt under 150 words and output only the enhanced prompt text."
            )

            content_parts.append(user_prompt)

            # Generate enhanced prompt
            response = self._model.generate_content(
                content_parts,
                generation_config=GenerationConfig(
                    temperature=0.4,
                    top_p=0.95,
                    top_k=40,
                    max_output_tokens=500,
                ),
                system_instruction=system_prompt,
            )

            if not response or not hasattr(response, "text"):
                logger.warning("Gemini returned empty response for prompt enhancement")
                return self._simple_enhance_prompt(
                    base_prompt, duration_seconds, aspect_ratio
                )

            enhanced_prompt = response.text.strip()
            logger.info("Enhanced prompt with Gemini")

            return enhanced_prompt

        except Exception as e:
            logger.error(f"Error enhancing prompt with Gemini: {e}")
            return self._simple_enhance_prompt(
                base_prompt, duration_seconds, aspect_ratio
            )

    def _simple_enhance_prompt(
        self, base_prompt: str, duration_seconds: int, aspect_ratio: str
    ) -> str:
        """
        Simple fallback prompt enhancement without Gemini.

        Args:
            base_prompt: Basic text description
            duration_seconds: Video duration in seconds
            aspect_ratio: Aspect ratio

        Returns:
            Enhanced prompt
        """
        # Standard cinematic enhancements that generally improve results
        enhancements = [
            "cinematic lighting",
            "shallow depth of field",
            "professional camera",
            "4K resolution",
            "high quality",
            "detailed textures",
        ]

        # Choose a random camera movement based on duration
        if duration_seconds >= 6:
            camera_movements = [
                "slow cinematic dolly in",
                "gentle pan from left to right",
                "slight tracking shot",
                "subtle zoom out",
            ]
            import random

            movement = random.choice(camera_movements)
            enhancements.append(movement)

        # Format the enhanced prompt
        enhanced_prompt = (
            f"Generate a {duration_seconds}-second video in {aspect_ratio} aspect ratio: "
            f"{base_prompt}. {', '.join(enhancements)}."
        )

        logger.info("Enhanced prompt with simple fallback method")
        return enhanced_prompt
