import pytest
import os
from topic_manager import TopicManager


@pytest.fixture
def test_topics_file(tmp_path):
    """Create a temporary topics file for testing"""
    return str(tmp_path / "test_topics.json")


@pytest.fixture
def topic_manager(test_topics_file):
    """Create a TopicManager instance with a test file"""
    manager = TopicManager(topics_file=test_topics_file)
    yield manager
    # Cleanup
    if os.path.exists(test_topics_file):
        os.remove(test_topics_file)


@pytest.fixture
def sample_topics():
    """Return a list of sample topics for testing"""
    return [
        "Write a story about a magical forest",
        "Write a story about a time traveler",
        "Write a story about a robot's first day at work",
    ]
