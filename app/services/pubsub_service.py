"""Service for handling Google Cloud Pub/Sub operations."""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

from app.config import settings

logger = logging.getLogger(__name__)


class PubSubService:
    """Service for publishing and subscribing to Pub/Sub topics."""

    def __init__(self):
        self._project_id = settings.GCP_PROJECT
        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()

        # Define topics and subscriptions
        self.TOPICS = {
            "video_scene": "video-scene-generation",
        }

        self.SUBSCRIPTIONS = {
            "video_scene": "video-scene-processor",
        }

    def ensure_topic_exists(self, topic_id: str) -> str:
        """
        Ensure a topic exists, creating it if necessary.

        Args:
            topic_id: The topic ID or name

        Returns:
            The full topic path
        """
        topic_path = self._publisher.topic_path(self._project_id, topic_id)

        try:
            self._publisher.get_topic(request={"topic": topic_path})
            logger.debug(f"Topic already exists: {topic_path}")
        except Exception:
            try:
                self._publisher.create_topic(request={"name": topic_path})
                logger.info(f"Topic created: {topic_path}")
            except AlreadyExists:
                logger.debug(f"Topic already exists (race condition): {topic_path}")

        return topic_path

    def ensure_subscription_exists(self, topic_id: str, subscription_id: str) -> str:
        """
        Ensure a subscription exists, creating it if necessary.

        Args:
            topic_id: The topic ID
            subscription_id: The subscription ID

        Returns:
            The full subscription path
        """
        topic_path = self._publisher.topic_path(self._project_id, topic_id)
        subscription_path = self._subscriber.subscription_path(
            self._project_id, subscription_id
        )

        try:
            self._subscriber.get_subscription(
                request={"subscription": subscription_path}
            )
            logger.debug(f"Subscription already exists: {subscription_path}")
        except Exception:
            try:
                self._subscriber.create_subscription(
                    request={"name": subscription_path, "topic": topic_path}
                )
                logger.info(f"Subscription created: {subscription_path}")
            except AlreadyExists:
                logger.debug(
                    f"Subscription already exists (race condition): {subscription_path}"
                )

        return subscription_path

    def publish_scene_generation_request(
        self, scene_id: str, prompt: str, params: Dict[str, Any]
    ) -> str:
        """
        Publish a request to generate a video scene.

        Args:
            scene_id: Unique identifier for the scene
            prompt: The scene prompt
            params: Additional parameters (duration, aspect_ratio, etc.)

        Returns:
            The published message ID
        """
        topic_id = self.TOPICS["video_scene"]
        topic_path = self.ensure_topic_exists(topic_id)

        # Prepare the message
        message = {
            "scene_id": scene_id,
            "prompt": prompt,
            "params": params,
        }

        # Publish the message
        data = json.dumps(message).encode("utf-8")
        future = self._publisher.publish(topic_path, data)
        message_id = future.result()

        logger.info(
            f"Published scene generation request for scene {scene_id}: {message_id}"
        )
        return message_id

    def publish_batch_scene_requests(self, scenes: List[Dict[str, Any]]) -> List[str]:
        """
        Publish multiple scene generation requests in parallel.

        Args:
            scenes: List of scene dictionaries with id, prompt, and params

        Returns:
            List of published message IDs
        """
        topic_id = self.TOPICS["video_scene"]
        topic_path = self.ensure_topic_exists(topic_id)

        message_ids = []
        futures = []

        # Publish all messages and collect futures
        for scene in scenes:
            message = {
                "scene_id": scene["id"],
                "prompt": scene["prompt"],
                "params": scene.get("params", {}),
            }

            data = json.dumps(message).encode("utf-8")
            future = self._publisher.publish(topic_path, data)
            futures.append((future, scene["id"]))

        # Wait for all futures to complete
        for future, scene_id in futures:
            try:
                message_id = future.result()
                message_ids.append(message_id)
                logger.info(f"Published scene request {scene_id}: {message_id}")
            except Exception as e:
                logger.error(f"Failed to publish scene request {scene_id}: {e}")

        return message_ids
