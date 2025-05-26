import os
import logging
from flask import Flask, jsonify, request
from worker_client import WorkerClient
from story_generator import generate_story, extract_image_prompts
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from youtube_uploader import upload_video
from datetime import datetime
import threading
import time
from timing_metrics import TimingMetrics
from topic_manager import TopicManager

# Google Cloud Monitoring imports
try:
    from google.cloud import monitoring_v3
    from google.cloud import logging as cloud_logging
    from google.cloud import error_reporting
    import google.cloud.logging
    CLOUD_MONITORING_AVAILABLE = True
except ImportError:
    CLOUD_MONITORING_AVAILABLE = False
    logging.warning("Google Cloud monitoring libraries not available. Running without cloud monitoring.")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Google Cloud Logging if available
if CLOUD_MONITORING_AVAILABLE:
    try:
        client = google.cloud.logging.Client()
        client.setup_logging()
        logger.info("Google Cloud Logging initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Cloud Logging: {e}")

# Initialize Flask app
app = Flask(__name__)

# Global variables
is_generating = False
is_initialized = False
last_generation_time = None
last_generation_status = None
timing_metrics = TimingMetrics()
topic_manager = None

# Initialize monitoring client
monitoring_client = None
error_client = None

if CLOUD_MONITORING_AVAILABLE:
    try:
        monitoring_client = monitoring_v3.MetricServiceClient()
        error_client = error_reporting.Client()
        logger.info("Google Cloud Monitoring clients initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize monitoring clients: {e}")

def send_custom_metric(metric_name: str, value: float, labels: dict = None):
    """Send a custom metric to Google Cloud Monitoring."""
    if not monitoring_client:
        return
    
    try:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            return
            
        project_name = f"projects/{project_id}"
        
        # Create the time series
        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/autovideo/{metric_name}"
        
        # Add labels
        if labels:
            for key, value in labels.items():
                series.metric.labels[key] = str(value)
        
        # Set the resource
        series.resource.type = "cloud_run_revision"
        series.resource.labels["service_name"] = "av-app"
        series.resource.labels["revision_name"] = os.getenv("K_REVISION", "unknown")
        series.resource.labels["location"] = "us-central1"
        
        # Create a data point
        point = monitoring_v3.Point()
        point.value.double_value = value
        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10 ** 9)
        point.interval.end_time.seconds = seconds
        point.interval.end_time.nanos = nanos
        series.points = [point]
        
        # Send the metric
        monitoring_client.create_time_series(
            name=project_name, 
            time_series=[series]
        )
        
    except Exception as e:
        logger.error(f"Failed to send custom metric {metric_name}: {e}")

def report_error(error: Exception, context: str = None):
    """Report an error to Google Cloud Error Reporting."""
    if error_client:
        try:
            error_client.report_exception(
                http_context=context
            )
        except Exception as e:
            logger.error(f"Failed to report error: {e}")
    
    # Always log the error locally as well
    logger.error(f"Error in {context}: {error}", exc_info=True)

def initialize_app():
    """Initialize the application and check required environment variables."""
    logger.info("Starting application initialization...")
    
    try:
        # Create necessary directories
        logger.info("Creating application directories...")
        os.makedirs('output', exist_ok=True)
        os.makedirs('secrets', exist_ok=True)
        os.makedirs('fonts', exist_ok=True)
        logger.info("Application directories created successfully")
        
        # Check required environment variables
        logger.info("Checking environment variables...")
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
        if not project_id:
            logger.warning("GOOGLE_CLOUD_PROJECT environment variable not set. Some features may not work.")
            return False
        
        logger.info(f"Application initialized successfully with project: {project_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}", exc_info=True)
        return False

@app.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        # Send health check metric
        send_custom_metric("health_check", 1.0, {"status": "healthy"})
        return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        report_error(e, "health_check")
        send_custom_metric("health_check", 0.0, {"status": "unhealthy"})
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/status')
def status():
    """Get the current status of video generation."""
    try:
        status_data = {
            "is_generating": is_generating,
            "is_initialized": is_initialized,
            "last_generation_time": last_generation_time,
            "last_generation_status": last_generation_status,
            "timing_metrics": timing_metrics.get_metrics()
        }
        
        # Send status metrics
        send_custom_metric("status_check", 1.0, {
            "generating": str(is_generating),
            "initialized": str(is_initialized)
        })
        
        return jsonify(status_data)
    except Exception as e:
        report_error(e, "status_check")
        return jsonify({"error": "Failed to get status"}), 500

@app.route('/generate', methods=['POST'])
def start_generation():
    """Start the video generation process."""
    global is_generating
    
    try:
        if is_generating:
            send_custom_metric("generation_request", 1.0, {"status": "rejected", "reason": "already_generating"})
            return jsonify({"error": "Video generation already in progress"}), 409
        
        if not is_initialized:
            send_custom_metric("generation_request", 1.0, {"status": "rejected", "reason": "not_initialized"})
            return jsonify({"error": "Application not properly initialized"}), 500
        
        # Send generation start metric
        send_custom_metric("generation_request", 1.0, {"status": "accepted"})
        send_custom_metric("generation_started", 1.0)
        
        # Start video generation in a background thread
        thread = threading.Thread(target=generate_video_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({"message": "Video generation started"})
        
    except Exception as e:
        report_error(e, "start_generation")
        send_custom_metric("generation_request", 1.0, {"status": "error"})
        return jsonify({"error": "Failed to start generation"}), 500

def generate_video_thread():
    """Background thread for video generation."""
    global is_generating, last_generation_status, topic_manager
    
    generation_start_time = time.time()
    
    try:
        is_generating = True
        # Start timing
        timing_metrics.start_pipeline()
        
        # Send pipeline start metric
        send_custom_metric("pipeline_started", 1.0)
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"/app/output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize topic manager and get next topic
        if topic_manager is None:
            topic_manager = TopicManager()
        story_prompt = topic_manager.get_next_topic()
        
        # Generate content
        timing_metrics.start_phase("story_generation")
        phase_start = time.time()
        story, prompt = generate_story(story_prompt)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "story_generation"})
        
        # Extract image prompts from the story
        image_prompts = extract_image_prompts(story)
        send_custom_metric("image_prompts_count", len(image_prompts))
        
        timing_metrics.start_phase("image_generation")
        phase_start = time.time()
        image_paths = generate_images(image_prompts, output_dir)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "image_generation"})
        send_custom_metric("images_generated", len(image_paths))
        
        timing_metrics.start_phase("voiceover_generation")
        phase_start = time.time()
        audio_path = os.path.join(output_dir, "voiceover.mp3")
        generate_voiceover(story, audio_path)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "voiceover_generation"})
        
        # Create worker
        timing_metrics.start_phase("worker_creation")
        phase_start = time.time()
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        worker_url = WorkerClient.create_worker(project_id)
        if not worker_url:
            raise Exception("Failed to create GPU worker")
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "worker_creation"})
        
        # Process video using worker
        timing_metrics.start_phase("video_processing")
        phase_start = time.time()
        worker = WorkerClient(worker_url)
        output_path = f"{output_dir}/final_video.mp4"
        success = worker.process_video(image_paths, output_path, audio_path)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "video_processing"})
        
        if not success:
            raise Exception("Video processing failed")
        
        # Upload to YouTube
        timing_metrics.start_phase("youtube_upload")
        phase_start = time.time()
        # Extract title and description from story
        story_lines = story.split('\n')
        title = story_lines[0].replace('Title: ', '')
        description = story_lines[1].replace('Description: ', '')
        # Add the full story as additional context
        description += "\n\nFull Story:\n" + "\n".join(story_lines[2:])
        upload_video(output_path, title, description)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric("phase_duration", phase_duration, {"phase": "youtube_upload"})
        
        # Calculate total pipeline duration
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric("pipeline_completed", 1.0, {"status": "success"})
        
        logger.info("Video generation and upload completed successfully")
        last_generation_status = "completed"
        
    except Exception as e:
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric("pipeline_completed", 1.0, {"status": "error"})
        
        report_error(e, "video_generation_pipeline")
        logger.error(f"Error generating video: {str(e)}")
        last_generation_status = f"error: {str(e)}"
    finally:
        is_generating = False
        timing_metrics.end_pipeline()
        send_custom_metric("pipeline_ended", 1.0)

# Initialize the application
try:
    is_initialized = initialize_app()
    logger.info(f"Application initialization result: {is_initialized}")
except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    is_initialized = False

# Expose the WSGI application
application = app

if __name__ == "__main__":
    # Start Flask server
    app.run(host='0.0.0.0', port=8080)
