# **AutoVideo v1 — AI Auto Video Generator**

An automated video generation pipeline that creates engaging videos from AI-generated stories, complete with images, voiceovers, and YouTube uploads.

## Architecture

The application consists of two main components:

1. **Main Application (av-app)**
   - Flask-based web service
   - Handles API endpoints and coordination
   - Manages video generation pipeline
   - Deployed on Google Cloud Run

2. **GPU Worker**
   - Dedicated service for video processing
   - Handles computationally intensive tasks
   - Optimized for GPU acceleration
   - Deployed on Google Cloud Run with GPU support

## Pipeline Process

1. **Story Generation**
   - Uses OpenAI to generate engaging stories
   - Extracts key scenes for visualization

2. **Image Generation**
   - Creates images for each scene
   - Ensures visual consistency

3. **Voiceover Generation**
   - Converts story text to natural-sounding speech
   - Uses ElevenLabs for high-quality voice synthesis

4. **Video Creation**
   - Combines images and voiceover
   - Adds transitions and effects
   - Optimizes for YouTube

5. **YouTube Upload**
   - Handles authentication and upload
   - Manages video metadata

## Setup

### Prerequisites

- Python 3.11+
- Docker
- Google Cloud SDK
- Required API keys:
  - OpenAI API Key
  - ElevenLabs API Key
  - YouTube API credentials
  - Google Cloud Project

### Environment Variables

```bash
OPENAI_API_KEY=your_openai_key
OPENAI_ORG_ID=your_org_id
ELAI_API_KEY=your_elai_key
DID_API_KEY=your_did_key
IMGUR_CLIENT_ID=your_imgur_client_id
IMGUR_CLIENT_SECRET=your_imgur_client_secret
ELEVENLABS_API_KEY=your_elevenlabs_key
PEXELS_API_KEY=your_pexels_key
YOUTUBE_CLIENT_ID=your_youtube_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret
YOUTUBE_PROJECT_ID=your_youtube_project_id
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
```

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/rezearcher/AutoVideo.v1.git
   cd AI-Auto-Video-Generator
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   .\venv\Scripts\activate  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python main.py
   ```

### Docker Build

1. Build the image:
   ```bash
   docker build -t av-app .
   ```

2. Run the container:
   ```bash
   docker run -p 8080:8080 av-app
   ```

## Deployment

### Google Cloud Run

1. Build and push the container:
   ```bash
   gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/av-app
   ```

2. Deploy the service:
   ```bash
   gcloud run deploy av-app \
     --image gcr.io/$GOOGLE_CLOUD_PROJECT/av-app \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated
   ```

## API Endpoints

- `GET /health` - Health check endpoint
- `GET /status` - Get current video generation status
- `POST /generate` - Start video generation process

## Monitoring

The application includes comprehensive logging and timing metrics for each phase of the video generation process. You can monitor the progress through the `/status` endpoint.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

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

# 🔄 **Split Architecture**

The application uses a split architecture with two main components:

1. **Web Application Container**
   - Handles HTTP requests and API endpoints
   - Manages story generation and image creation
   - Coordinates the video generation process
   - Runs on standard Cloud Run instances

2. **GPU Worker Container**
   - Dedicated container for video processing
   - Uses NVIDIA CUDA for hardware acceleration
   - Handles video rendering and encoding
   - Runs on GPU-enabled instances
   - Communicates with main app via HTTP

This architecture provides several benefits:
- Better resource utilization
- Improved scalability
- Independent scaling of web and processing components
- Cost optimization (GPU only when needed)
- Better error isolation

The worker container is built using `Dockerfile.gpu-worker` and includes:
- NVIDIA CUDA runtime
- FFmpeg with CUDA support
- FastAPI for worker API endpoints
- Async processing capabilities

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

## Secret Management

### GitHub Actions Secrets
The application uses GitHub Actions secrets for secure deployment. Required secrets:

```yaml
# GitHub Actions Secrets
OPENAI_API_KEY: OpenAI API key for story generation
ELEVENLABS_API_KEY: ElevenLabs API key for voice synthesis
WIF_PROVIDER: Google Cloud Workload Identity Provider
WIF_SERVICE_ACCOUNT: Google Cloud Service Account for deployment
```

### Cloud Run Environment Variables
The application uses environment variables in Cloud Run for runtime configuration:

```yaml
# Cloud Run Environment Variables
OPENAI_API_KEY: Set from GitHub Actions secret
ELEVENLABS_API_KEY: Set from GitHub Actions secret
YOUTUBE_ENABLED: true/false to control YouTube upload feature
GOOGLE_CLOUD_PROJECT: Project ID for Google Cloud services
```

### Important Notes
1. Never store secrets in files or commit them to the repository
2. Use GitHub Actions secrets for deployment-time configuration
3. Use Cloud Run environment variables for runtime configuration
4. The service account must have the following roles:
   - Cloud Run Admin
   - Service Account User
   - Storage Admin

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
