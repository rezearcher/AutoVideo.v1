from fastapi import FastAPI, BackgroundTasks
import subprocess
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.post("/process")
async def process_video(job_data: dict, background_tasks: BackgroundTasks):
    logging.info(f"Received job: {job_data}")
    background_tasks.add_task(render_video, job_data)
    return {"status": "processing"}

def render_video(job_data):
    try:
        logging.info(f"Rendering video: {job_data}")
        subprocess.run([
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", job_data["input"],
            "-c:v", "h264_nvenc", "-preset", "fast", job_data["output"]
        ], check=True)
        logging.info(f"Video rendered successfully: {job_data['output']}")
    except Exception as e:
        logging.error(f"Error rendering video: {e}") 