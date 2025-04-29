# **AutoVideo v1 — AI Auto Video Generator**

A fully automated, AI-powered storytelling video generator.

- Generates a story from a text prompt using **OpenAI GPT**.
- Creates images using **OpenAI DALL-E**.
- Adds voiceover using **ElevenLabs**.
- Assembles final video output using **MoviePy** and **FFmpeg**.

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
| V1 | Generate basic videos, upload to YouTube via automation |
| V2 | Improve video quality (AI scene analysis, dynamic editing) |
| V3 | Inject trend detection to create timely, viral content |
| Beyond | Expand to TikTok, Instagram, trend scraping, analytics |

---

# 📦 **Getting Started**

## 1. Prerequisites

- Python 3.8+
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

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install spacy model
python -m spacy download en_core_web_sm
```

---

## 3. API Keys Configuration

Create a `.env` file in the root directory:

```plaintext
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

- [OpenAI API Key](https://platform.openai.com/account/api-keys)
- [ElevenLabs API Key](https://beta.elevenlabs.io/subscription)

**Important:**  
Keep your API keys secret. Never commit `.env` to GitHub.

---

## 4. Font Configuration

Edit `caption_generator.py` with your system's font path:

| OS | Example |
|:---|:---|
| Windows | `C:\Windows\Fonts\Arial.ttf` |
| Linux | `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf` |

---

## 5. Usage

Run manually first to verify:

```bash
python main.py
```

- Input your prompt when asked.
- Video will be output to the `/output` folder.

---

# 🐳 **Containerization**

To build and run the container:

```bash
docker build -t autovideo .
docker run --env-file .env autovideo
```

*Output video is mounted to a local volume inside the container (WIP — final structure coming soon).*

---

# ⚙️ **CI/CD Pipeline (GitHub Actions)**

Planned GitHub Actions workflow will:
- Build Docker image automatically
- Trigger video generation job
- Upload completed video to YouTube

**[To Be Finalized After V1 Cloud Deployment]**

---

# 🛰️ **Planned Cloud Deployment**

V1 cloud setup:
- Deploy container via **Google Cloud Run** or **GCP VM**
- Trigger scheduled runs via **GCP Scheduler** or **cronjob**
- Upload videos directly from cloud to YouTube

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

