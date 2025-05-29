#!/usr/bin/env python3
"""
Fast-Lane GPU Renderer Launcher

Intelligently selects the most cost-effective GPU configuration 
and launches a Compute Engine VM for video rendering when Vertex AI 
is too slow or times out.
"""

import json
import os
import subprocess
import sys
from uuid import uuid4

import yaml


def load_gpu_catalog():
    """Load GPU catalog with cost and performance data"""
    catalog_path = os.path.join(os.path.dirname(__file__), "../gpu_catalog.yml")
    with open(catalog_path, 'r') as f:
        return yaml.safe_load(f)


def estimate_costs_and_select_gpu(video_length_s=180, baseline_speed=20):
    """
    Estimate costs for each GPU option and select the most cost-effective
    
    Args:
        video_length_s: Video duration in seconds
        baseline_speed: Baseline T4 processing speed (seconds per video second)
    
    Returns:
        tuple: (cost, gpu_key, estimated_runtime, gpu_config)
    """
    catalog = load_gpu_catalog()
    base_time = video_length_s * baseline_speed
    choices = []
    
    for key, info in catalog.items():
        estimated_time = base_time / info["speed_factor"]
        estimated_cost = info["cost_per_hour"] * (estimated_time / 3600)
        choices.append((estimated_cost, key, estimated_time, info))
    
    # Sort by cost and return the cheapest option
    choices.sort(key=lambda x: x[0])
    
    print("💰 Cost Analysis:")
    for cost, key, time, info in choices:
        print(f"  {key.upper():>4}: ${cost:5.2f} ({time:4.0f}s) - {info['machine']}")
    
    return choices[0]  # Return cheapest option


def create_startup_script(project_id, staging_bucket, output_bucket, job_id=""):
    """Create the VM startup script for video rendering"""
    return f"""#!/bin/bash
set -xe

# Log everything
exec > >(tee /var/log/startup.log) 2>&1

echo "🚀 Starting AutoVideo Fast Render $(date)"
echo "📋 Job ID: {job_id}"

# Install dependencies
apt-get update
apt-get install -y ffmpeg python3-pip git

# Install Python packages
pip3 install moviepy google-cloud-storage pillow opencv-python

# Create workspace
mkdir -p /workspace
cd /workspace

# Download job assets if job ID provided
if [ "{job_id}" != "" ]; then
    echo "📦 Downloading job assets for {job_id}..."
    gsutil -m cp -r gs://{staging_bucket}/jobs/{job_id}/* /workspace/ || echo "Failed to download job assets"
    
    # Check if we have the required files
    if [ -f "/workspace/story.json" ]; then
        echo "✅ Job assets downloaded successfully"
        
        # Extract job data
        python3 -c "
import json
with open('/workspace/story.json', 'r') as f:
    job_data = json.load(f)
    
print('Story:', job_data['story'][:100] + '...')
print('Images:', len(job_data['image_urls']))
print('Audio URL:', job_data['audio_url'])
"
    else
        echo "❌ No job assets found - downloading fallback gpu_worker.py"
        gsutil cp gs://{staging_bucket}/gpu_worker.py /workspace/ || echo "No fallback worker found"
    fi
else
    echo "📦 No job ID provided - downloading fallback assets"
    gsutil -m cp -r gs://{staging_bucket}/* /workspace/ || echo "No staging assets found"
    gsutil cp gs://{staging_bucket}/gpu_worker.py /workspace/ || echo "Downloading from backup..."
fi

# Create video render script for job-based processing
cat > /workspace/render_job.py << 'EOF'
#!/usr/bin/env python3
import json
import os
import sys
from google.cloud import storage

def download_assets(job_data):
    """Download image and audio assets from Cloud Storage"""
    storage_client = storage.Client()
    
    # Download images
    image_paths = []
    for i, image_url in enumerate(job_data['image_urls']):
        bucket_name = image_url.split('/')[2]
        blob_path = '/'.join(image_url.split('/')[3:])
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        local_path = f"/workspace/image_{i:03d}.jpg"
        blob.download_to_filename(local_path)
        image_paths.append(local_path)
    
    # Download audio
    audio_url = job_data['audio_url']
    bucket_name = audio_url.split('/')[2]
    blob_path = '/'.join(audio_url.split('/')[3:])
    
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    audio_path = "/workspace/voiceover.mp3"
    blob.download_to_filename(audio_path)
    
    return image_paths, audio_path

def create_video(image_paths, audio_path, story):
    """Create video using MoviePy"""
    try:
        from moviepy import CompositeVideoClip, ImageClip, VideoFileClip
        from moviepy.video.fx import resize
        import moviepy.audio.fx.all as afx
        
        print(f"🎬 Creating video with {len(image_paths)} images...")
        
        # Load audio to get duration
        audio_clip = VideoFileClip(audio_path).audio
        duration = audio_clip.duration
        clip_duration = duration / len(image_paths)
        
        # Create image clips
        clips = []
        for i, img_path in enumerate(image_paths):
            img_clip = ImageClip(img_path, duration=clip_duration)
            img_clip = img_clip.resize(height=720)  # 720p
            clips.append(img_clip)
        
        # Concatenate clips
        video = CompositeVideoClip(clips, method='chain')
        
        # Add audio
        final_video = video.set_audio(audio_clip)
        
        # Write output
        output_path = "/workspace/final.mp4"
        final_video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='/workspace/temp-audio.m4a',
            remove_temp=True
        )
        
        print(f"✅ Video created: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"❌ Video creation failed: {e}")
        return None

def main():
    if os.path.exists('/workspace/story.json'):
        print("📖 Processing job-based render...")
        
        with open('/workspace/story.json', 'r') as f:
            job_data = json.load(f)
        
        # Download assets
        print("📥 Downloading assets...")
        image_paths, audio_path = download_assets(job_data)
        
        # Create video
        video_path = create_video(image_paths, audio_path, job_data['story'])
        
        if video_path and os.path.exists(video_path):
            print("✅ Video render completed successfully")
            return True
        else:
            print("❌ Video render failed")
            return False
    else:
        print("❌ No job data found")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
EOF

# Run the render
echo "🎬 Starting video render..."
python3 /workspace/render_job.py

# Check if video was created
if [ -f "/workspace/final.mp4" ]; then
    echo "📤 Uploading result..."
    timestamp=$(date +%s)
    output_path="renders/$timestamp-video.mp4"
    gsutil cp /workspace/final.mp4 gs://{output_bucket}/$output_path
    
    echo "✅ Render complete: gs://{output_bucket}/$output_path"
else
    echo "❌ No video file created"
    exit 1
fi

# Clean shutdown
echo "🔌 Shutting down..."
shutdown -h now
"""


def launch_vm(gpu_config, gpu_key, vm_name, project_id, zone="us-central1-a"):
    """Launch the Compute Engine VM with the selected GPU configuration"""
    
    # Create startup script
    staging_bucket = os.getenv("STAGING_BUCKET", f"{project_id}-staging")
    output_bucket = os.getenv("OUTPUT_BUCKET", f"{project_id}-outputs")
    job_id = os.getenv("RENDER_JOB_ID", "")
    
    startup_script = create_startup_script(project_id, staging_bucket, output_bucket, job_id)
    
    # Write startup script to file
    startup_file = f"/tmp/startup-{vm_name}.sh"
    with open(startup_file, 'w') as f:
        f.write(startup_script)
    
    # Build gcloud command
    cmd = [
        "gcloud", "compute", "instances", "create", vm_name,
        f"--project={project_id}",
        f"--zone={zone}",
        f"--machine-type={gpu_config['machine']}",
        "--maintenance-policy=TERMINATE",
        "--no-restart-on-failure",
        "--boot-disk-size=50GB",
        "--boot-disk-type=pd-ssd",
        "--image-family=ubuntu-2004-lts",
        "--image-project=ubuntu-os-cloud",
        "--scopes=https://www.googleapis.com/auth/cloud-platform",
        f"--metadata-from-file=startup-script={startup_file}",
        "--tags=autovideo-render"
    ]
    
    # Add GPU accelerator if not CPU-only
    if gpu_config['accelerator'] != "none":
        cmd.append(f"--accelerator=type={gpu_config['accelerator']},count=1")
    
    print(f"🚀 Launching VM: {vm_name}")
    print(f"   Machine: {gpu_config['machine']}")
    print(f"   GPU: {gpu_config['accelerator']}")
    print(f"   Zone: {zone}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ VM launched successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to launch VM: {e}")
        print(f"Error output: {e.stderr}")
        return False
    finally:
        # Clean up temp file
        if os.path.exists(startup_file):
            os.remove(startup_file)


def main():
    """Main function to launch fast render VM"""
    # Configuration
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
    video_length = float(os.getenv("VIDEO_LENGTH_S", "180"))
    baseline_speed = float(os.getenv("BASELINE_T4_SPEED_S_PER_S", "20"))
    zone = os.getenv("RENDER_ZONE", "us-central1-a")
    
    print("🎯 AutoVideo Fast-Lane Renderer")
    print(f"   Project: {project_id}")
    print(f"   Video Length: {video_length}s")
    print(f"   Zone: {zone}")
    print()
    
    # Select optimal GPU configuration
    cost, gpu_key, runtime, gpu_config = estimate_costs_and_select_gpu(
        video_length, baseline_speed
    )
    
    print()
    print(f"🎯 Selected: {gpu_key.upper()}")
    print(f"   Machine: {gpu_config['machine']}")
    print(f"   Estimated time: {runtime:.0f}s ({runtime/60:.1f}m)")
    print(f"   Estimated cost: ${cost:.2f}")
    print()
    
    # Generate unique VM name
    vm_name = f"av-render-{uuid4().hex[:6]}"
    
    # Launch the VM
    success = launch_vm(gpu_config, gpu_key, vm_name, project_id, zone)
    
    if success:
        print(f"🎉 Fast render VM '{vm_name}' is starting up!")
        print(f"   Monitor with: gcloud compute instances list --filter='name:{vm_name}'")
        print(f"   Logs: gcloud compute instances get-serial-port-output {vm_name} --zone={zone}")
    else:
        print("💥 Failed to launch fast render VM")
        sys.exit(1)


if __name__ == "__main__":
    main() 