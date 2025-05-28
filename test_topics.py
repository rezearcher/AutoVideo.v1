#!/usr/bin/env python3

import os
import sys
from topic_manager import TopicManager

# Set up environment
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")


def test_topic_manager():
    try:
        print("🧪 Testing TopicManager...")
        tm = TopicManager()
        print(f"📝 Available topics: {len(tm.topics)}")
        print(f"🔄 Used topics: {len(tm.used_topics)}")

        if not tm.topics and not tm.used_topics:
            print("⚠️ No topics found, forcing generation...")
            tm.force_update_topics()
            print(f"✅ Generated {len(tm.topics)} topics")

        if tm.topics:
            print("📋 Sample topics:")
            for i, topic in enumerate(tm.topics[:3]):
                print(f"  {i+1}. {topic}")

            print("\n🎯 Getting next topic...")
            next_topic = tm.get_next_topic()
            print(f"Selected: {next_topic}")
        else:
            print("❌ No topics available after generation")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_topic_manager()
