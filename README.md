# **AutoVideo v1 — AI Auto Video Generator**

A fully automated, AI-powered storytelling video generator.

- Generates a story from a text prompt using **OpenAI GPT**.
- Creates images using **OpenAI DALL-E**.
- Adds voiceover using **ElevenLabs**.
- Assembles final video output using **MoviePy** and **FFmpeg**.
- Automatically uploads to **YouTube**.
- Runs on **Google Cloud Run** with daily scheduled execution.

**V1 Focus:**  
Create a video autonomously, containerize it, deploy it to the cloud, and automatically upload to **YouTube**.

---

# ✨ **Demo Examples**
[![Example 0](https://img.youtube.com/vi/hV4t2yW-RUk/0.jpg)](https://www.youtube.com/watch?v=hV4t2yW-RUk)
[![Example 1](https://img.youtube.com/vi/Vzcras5Snyo/0.jpg)](https://www.youtube.com/watch?v=Vzcras5Snyo)

---

# 🚀 **Project Goals (2025 Rollout)**

| Phase | Goal |
|:---|:---|
| V1 | ✅ Generate basic videos, upload to YouTube via automation |
| V2 | Improve video quality (AI scene analysis, dynamic editing) |
| V3 | Inject trend detection to create timely, viral content |
| Beyond | Expand to TikTok, Instagram, trend scraping, analytics |

---

# 📦 **Getting Started**

## 1. Prerequisites

- Python 3.8+ (pyenv recommended)
- Docker + Docker Compose (for containerization)
- GitHub account (for repo + CI/CD)
- Google Cloud / YouTube API credentials
- FFmpeg installed locally (`brew install ffmpeg` or `apt install ffmpeg`)

---

## 2. Environment Setup

```bash
# Clone the repository
git clone https://github.com/YOURNAMEHERE/AutoVideo.git
cd AutoVideo

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package in development mode
pip install -e .

# Install development dependencies (optional)
pip install -r requirements-dev.txt

# Install spacy model
python -m spacy download en_core_web_sm
```

---

## 3. Project Structure

```
AI-Auto-Video-Generator/
├── .github/               # GitHub Actions workflows
│   └── workflows/        # CI/CD configuration
├── .venv/                # Virtual environment
├── output/               # Generated videos
│   ├── audio/           # Generated audio files
│   ├── images/          # Generated images
│   ├── logs/            # Application logs
│   ├── text/            # Generated text content
│   └── video/           # Final video output
├── scripts/             # Utility scripts
├── youtube_uploader/    # YouTube upload functionality
├── .env                 # Environment variables (create from .env.example)
├── .env.example        # Example environment variables
├── main.py             # Main entry point
├── story_generator.py  # Story generation using GPT
├── image_generator.py  # Image generation using DALL-E
├── voiceover_generator.py # Voice generation using ElevenLabs
├── video_creator.py    # Video assembly using MoviePy
├── topic_manager.py    # Topic management and generation
├── output_manager.py   # Output file management
├── setup.py           # Package setup configuration
├── requirements.txt   # Core dependencies
└── requirements-dev.txt # Development dependencies
```

---

## 4. API Keys Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required API keys:
- OpenAI API Key (for story and image generation)
- ElevenLabs API Key (for voice generation)
- YouTube API credentials (for video upload)
- Stability AI API Key (for image generation)

**Important:**  
Keep your API keys secret. Never commit `.env` to GitHub.

---

## 5. Usage

### Local Development

Run the application using the installed command:

```bash
ai-video-gen
```

Or run directly:

```bash
python main.py
```

### Docker

Build and run the container:

```bash
docker build -t autovideo .
docker run --env-file .env autovideo
```

### Cloud Run Deployment

The application is automatically deployed to Google Cloud Run via GitHub Actions. The workflow:

1. Builds the Docker image
2. Pushes to Google Container Registry
3. Deploys to Cloud Run
4. Runs daily at 9 AM EST

To deploy manually:

```bash
gcloud run deploy av-app \
  --image us-central1-docker.pkg.dev/PROJECT_ID/av-app/av-app:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

The application will:
1. Generate a story from a prompt
2. Create images for key scenes
3. Generate voiceover narration
4. Assemble the final video
5. Upload to YouTube automatically

Output files will be saved in the `/output` directory, organized by type and timestamp.

---

# 🐳 **Containerization**

The application is containerized using Docker and includes:

- Python 3.11 base image
- FFmpeg for video processing
- Gunicorn for production serving
- Health checks and proper logging
- Non-root user for security
- Proper file permissions

---

# ⚙️ **Development**

## Testing

Run tests with pytest:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=.
```

## Code Quality

Format code:

```bash
black .
flake8
mypy .
```

## Documentation

Build documentation:

```bash
cd docs
make html
```

---

# 🛰️ **Cloud Deployment**

The application is deployed to Google Cloud Run with:

- Daily scheduled execution (9 AM EST)
- Automatic container builds
- Environment variable management
- Health monitoring
- Proper logging
- YouTube integration

Required GCP setup:
1. Enable required APIs (Cloud Run, Container Registry)
2. Create service account with necessary permissions
3. Configure GitHub Actions secrets

---

# 📈 **Future Enhancements (V2+)**

- Smarter video editing (scene analysis, pacing control)
- Auto-generated thumbnails
- Trend scraping (TikTok, YouTube, Instagram)
- Dynamic title/caption/hashtag injection
- Full multi-platform publishing
- Analytics tracking and performance dashboards

---

# 🧠 **Notes and Warnings**

- AI generation can sometimes fail due to API limits or bad prompts — retries will be implemented.
- This project will evolve rapidly — check for updated branches.
- This repo **starts simple on purpose** — foundation first, fancy later.

---

# 🛠️ **Contributing**

Right now this is a **personal/internal project**.  
Future contributors will follow a simple fork + pull request model.

---

# 👨‍💻 **Author**

**Rez E. Archer**  
- DevOps Architect | Full Stack Developer | Builder of Silent Empires  
- [probably.ninja (coming soon)](#)

---

# 🏴 **License**

MIT License (free to use, modify, distribute — with attribution if public.)

---

# Testing GitHub Actions
