import json
import random
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class TopicManager:
    def __init__(self, topics_file="topics.json", max_topics=10, update_interval_days=7):
        self.topics_file = topics_file
        self.max_topics = max_topics
        self.update_interval_days = update_interval_days
        self.topics = []
        self.used_topics = []
        self.last_update = None
        self._load_topics()
        
    def _load_topics(self):
        """Load topics from JSON file or create new file if it doesn't exist."""
        if os.path.exists(self.topics_file):
            try:
                with open(self.topics_file, 'r') as f:
                    data = json.load(f)
                    self.topics = data.get('topics', [])
                    self.used_topics = data.get('used', [])
                    self.last_update = datetime.fromisoformat(data.get('last_update', datetime.min.isoformat()))
            except json.JSONDecodeError:
                self._initialize_topics()
        else:
            self._initialize_topics()
            
    def _save_topics(self):
        """Save current topics and used topics to JSON file."""
        with open(self.topics_file, 'w') as f:
            json.dump({
                'topics': self.topics,
                'used': self.used_topics,
                'last_update': self.last_update.isoformat()
            }, f, indent=2)
            
    def _initialize_topics(self):
        """Initialize topics by generating new ones from GPT."""
        self.topics = []
        self.used_topics = []
        self.last_update = datetime.now()
        self._generate_new_topics()
        
    def _generate_new_topics(self):
        """Generate new topics using GPT."""
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a creative writing assistant. Generate unique and engaging story prompts. NEVER include prompts about bookstores, libraries, or books coming to life. Focus on diverse themes like adventure, mystery, science fiction, fantasy, and drama."},
                    {"role": "user", "content": f"Generate {self.max_topics} unique and creative story prompts. Each prompt should start with 'Write a story about'. Make them diverse and interesting. DO NOT include any prompts about bookstores, libraries, or books."}
                ],
                max_tokens=500,
                temperature=0.9
            )
            
            content = response.choices[0].message.content.strip()
            new_topics = []
            for line in content.split('\n'):
                if line.strip().startswith('Write a story about'):
                    # Skip any prompts about books/libraries/bookstores
                    if not any(word in line.lower() for word in ['book', 'library', 'bookstore']):
                        new_topics.append(line.strip())
                    
            # Update topics
            self.topics = new_topics[:self.max_topics]
            self.last_update = datetime.now()
            self._save_topics()
            
        except Exception as e:
            print(f"Error generating topics: {str(e)}")
            self._use_fallback_topics()
            
    def _use_fallback_topics(self):
        """Use fallback topics if GPT generation fails."""
        self.topics = [
            "Write a story about a mysterious island that appears once every hundred years",
            "Write a story about a time traveler who changes history by accident",
            "Write a story about a robot who develops human emotions"
        ]
        self.last_update = datetime.now()
        self._save_topics()
            
    def _check_and_update_topics(self):
        """Check if topics need to be updated based on the interval."""
        if not self.last_update:
            self._generate_new_topics()
            return
            
        time_since_update = datetime.now() - self.last_update
        if time_since_update > timedelta(days=self.update_interval_days):
            self._generate_new_topics()
            
    def get_next_topic(self):
        """Get the next topic while ensuring it hasn't been used in the last selection."""
        if not self.topics:
            # If no topics available, reset by moving all used topics back except the last used one
            if not self.used_topics:
                # If no used topics either, generate new ones
                self._generate_new_topics()
            else:
                # Move all but the last used topic back to available topics
                last_used = self.used_topics[-1] if self.used_topics else None
                self.topics = [topic for topic in self.used_topics[:-1] if topic != last_used]
                self.used_topics = [last_used] if last_used else []
                
                # If still no topics, generate new ones
                if not self.topics:
                    self._generate_new_topics()
        
        # Select a random topic from available ones
        selected_topic = random.choice(self.topics)
        self.topics.remove(selected_topic)
        self.used_topics.append(selected_topic)
        self._save_topics()
        return selected_topic
        
    def force_update_topics(self):
        """Force an update of the topics."""
        self._generate_new_topics()
        
    def add_topic(self, topic):
        """Add a new topic to the list if it doesn't already exist."""
        if topic not in self.topics:
            self.topics.append(topic)
            self._save_topics()
            
    def remove_topic(self, topic):
        """Remove a topic from the list."""
        if topic in self.topics:
            self.topics.remove(topic)
            self._save_topics()
            
    def list_topics(self):
        """Return all available topics."""
        return self.topics
        
    def list_used_topics(self):
        """Return all used topics."""
        return self.used_topics