import unittest
import os
import json
from datetime import datetime, timedelta
from topic_manager import TopicManager


class TestTopicManager(unittest.TestCase):
    def setUp(self):
        self.test_topics_file = "test_topics.json"
        self.topic_manager = TopicManager(topics_file=self.test_topics_file)

    def tearDown(self):
        if os.path.exists(self.test_topics_file):
            os.remove(self.test_topics_file)

    def test_initialization(self):
        """Test that TopicManager initializes with default values"""
        self.assertIsInstance(self.topic_manager.topics, list)
        self.assertIsInstance(self.topic_manager.used_topics, list)
        self.assertIsInstance(self.topic_manager.last_update, datetime)

    def test_add_topic(self):
        """Test adding a new topic"""
        test_topic = "Write a story about a test topic"
        self.topic_manager.add_topic(test_topic)
        self.assertIn(test_topic, self.topic_manager.topics)

    def test_remove_topic(self):
        """Test removing a topic"""
        test_topic = "Write a story about a test topic"
        self.topic_manager.add_topic(test_topic)
        self.topic_manager.remove_topic(test_topic)
        self.assertNotIn(test_topic, self.topic_manager.topics)

    def test_get_next_topic(self):
        """Test getting the next topic"""
        test_topic = "Write a story about a test topic"
        self.topic_manager.add_topic(test_topic)
        next_topic = self.topic_manager.get_next_topic()
        self.assertEqual(next_topic, test_topic)
        self.assertIn(test_topic, self.topic_manager.used_topics)

    def test_topic_rotation(self):
        """Test that topics rotate properly"""
        topics = [
            "Write a story about topic 1",
            "Write a story about topic 2",
            "Write a story about topic 3",
        ]
        for topic in topics:
            self.topic_manager.add_topic(topic)

        # Get all topics
        used_topics = []
        for _ in range(len(topics)):
            used_topics.append(self.topic_manager.get_next_topic())

        # Verify all topics were used
        self.assertEqual(set(used_topics), set(topics))

    def test_force_update(self):
        """Test forcing a topic update"""
        original_topics = self.topic_manager.topics.copy()
        self.topic_manager.force_update_topics()
        self.assertNotEqual(original_topics, self.topic_manager.topics)


if __name__ == "__main__":
    unittest.main()
