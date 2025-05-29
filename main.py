# Auto Video Generator - Cloud Native
# Updated: 2025-05-28 - GPU compatibility fixes included
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import google.auth
from flask import Flask, jsonify, request

from image_generator import generate_images
from story_generator import extract_image_prompts, generate_story, get_openai_client
from timing_metrics import TimingMetrics
from topic_manager import TopicManager
from voiceover_generator import generate_voiceover
from youtube_uploader import upload_video

# Optional import for local video processing fallback
try:
    from video_creator import create_video

    LOCAL_VIDEO_PROCESSING_AVAILABLE = True
except ImportError as e:
    LOCAL_VIDEO_PROCESSING_AVAILABLE = False
    logging.warning(f"Local video processing not available: {e}")
    create_video = None

# Google Cloud Monitoring imports
try:
    import google.cloud.logging
    from google.cloud import error_reporting, monitoring_v3

    CLOUD_MONITORING_AVAILABLE = True
except ImportError:
    CLOUD_MONITORING_AVAILABLE = False
    logging.warning(
        "Google Cloud monitoring libraries not available. Running without cloud monitoring."
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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
last_generation_status = "ready"
timing_metrics = TimingMetrics()
topic_manager = None
vertex_gpu_service = None  # Global GPU service instance

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

# Rate limiting storage (in-memory for simplicity)
request_counts = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_MAX_REQUESTS = 10  # Max requests per window

# Application initialization flag
app_initialized = False


def send_custom_metric(metric_name: str, value: float, labels: dict = None):
    """Send a custom metric to Google Cloud Monitoring."""
    if not monitoring_client:
        return

    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
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
        nanos = int((now - seconds) * 10**9)
        point.interval.end_time.seconds = seconds
        point.interval.end_time.nanos = nanos
        series.points = [point]

        # Send the metric
        monitoring_client.create_time_series(name=project_name, time_series=[series])

    except Exception as e:
        logger.error(f"Failed to send custom metric {metric_name}: {e}")


def report_error(error: Exception, context: str = None):
    """Report an error to Google Cloud Error Reporting."""
    if error_client:
        try:
            error_client.report_exception(http_context=context)
        except Exception as e:
            logger.error(f"Failed to report error: {e}")

    # Always log the error locally as well
    logger.error(f"Error in {context}: {error}", exc_info=True)


def check_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limits."""
    now = datetime.now()
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)

    # Clean old requests
    request_counts[client_ip] = [
        req_time for req_time in request_counts[client_ip] if req_time > cutoff
    ]

    # Check if under limit
    if len(request_counts[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        send_custom_metric("rate_limit_exceeded", 1.0, {"client_ip": client_ip})
        return False

    # Add current request
    request_counts[client_ip].append(now)
    return True


def log_api_call(api_name: str, success: bool, duration: float = None):
    """Log external API calls for monitoring."""
    logger.info(f"API Call: {api_name} - Success: {success} - Duration: {duration}s")
    send_custom_metric(
        "external_api_call",
        1.0,
        {
            "api": api_name,
            "success": str(success),
            "duration": str(duration) if duration else "unknown",
        },
    )


@app.before_request
def before_request():
    """Apply rate limiting to all requests."""
    client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)

    # Skip rate limiting for health checks
    if request.path in ["/health", "/health/openai"]:
        return

    if not check_rate_limit(client_ip):
        return (
            jsonify(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds",
                }
            ),
            429,
        )


def initialize_app():
    """Initialize the application and check required environment variables."""
    global vertex_gpu_service, app_initialized

    logger.info("Starting application initialization...")

    # Log service account at startup
    try:
        creds, project = google.auth.default()

        # Try to get service account email from metadata server (more reliable in Cloud Run)
        try:
            import requests

            metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
            headers = {"Metadata-Flavor": "Google"}
            response = requests.get(metadata_url, headers=headers, timeout=5)
            if response.status_code == 200:
                sa_email = response.text.strip()
            else:
                sa_email = getattr(creds, "service_account_email", "Unknown")
        except Exception:
            sa_email = getattr(creds, "service_account_email", "Unknown")

        logger.info(f"🔑 Starting with service account: {sa_email}")
        logger.info(f"📍 Project: {project}")
    except Exception as e:
        logger.error(f"❌ Could not determine service account: {e}")

    try:
        # Create necessary directories
        logger.info("Creating application directories...")
        os.makedirs("output", exist_ok=True)
        os.makedirs("secrets", exist_ok=True)
        os.makedirs("fonts", exist_ok=True)
        logger.info("Application directories created successfully")

        # Check required environment variables
        logger.info("Checking environment variables...")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

        if not project_id:
            logger.warning(
                "GOOGLE_CLOUD_PROJECT environment variable not set. Some features may not work."
            )
            return False

        # Validate OpenAI API key
        logger.info("Validating OpenAI API key...")
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.critical("OPENAI_API_KEY is missing! Video generation will fail.")
            return False
        elif len(openai_key) < 20:  # Basic sanity check
            logger.critical(
                f"OPENAI_API_KEY appears invalid (length={len(openai_key)}). Expected longer key."
            )
            return False
        else:
            logger.info(
                f"OPENAI_API_KEY loaded successfully (length={len(openai_key)})"
            )

        # Validate other critical API keys
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        if not elevenlabs_key:
            logger.warning("ELEVENLABS_API_KEY is missing! Voice generation may fail.")
        else:
            logger.info(f"ELEVENLABS_API_KEY loaded (length={len(elevenlabs_key)})")

        pexels_key = os.getenv("PEXELS_API_KEY")
        if not pexels_key:
            logger.warning("PEXELS_API_KEY is missing! Image fallback may fail.")
        else:
            logger.info(f"PEXELS_API_KEY loaded (length={len(pexels_key)})")

        # Initialize global Vertex AI GPU service
        logger.info("Initializing global VertexGPUJobService...")
        try:
            from vertex_gpu_service import VertexGPUJobService

            vertex_gpu_service = VertexGPUJobService(project_id=project_id)
            logger.info("✅ Global VertexGPUJobService initialized successfully")
        except Exception as gpu_error:
            logger.warning(f"⚠️ Failed to initialize VertexGPUJobService: {gpu_error}")
            logger.warning(
                "Video generation will be unavailable, but app will continue"
            )
            vertex_gpu_service = None

        app_initialized = True
        logger.info(f"Application initialized successfully with project: {project_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}", exc_info=True)
        return False


@app.route("/health")
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


@app.route("/health/openai")
def openai_health_check():
    """Test OpenAI API connectivity and model access."""
    try:
        # Set the API key
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return (
                jsonify({"status": "error", "error": "OPENAI_API_KEY not found"}),
                500,
            )

        # Test OpenAI API connectivity using the same robust client as story generation
        logger.info("Testing OpenAI API connectivity...")

        # Import the robust client from story_generator
        client = get_openai_client()

        # Simple API test - list models (lightweight call)
        models = client.models.list()
        model_count = len(list(models))

        logger.info(f"OpenAI API test successful - {model_count} models available")
        send_custom_metric("openai_health_check", 1.0, {"status": "healthy"})

        return jsonify(
            {
                "status": "ok",
                "models_count": model_count,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"OpenAI health check failed: {e}", exc_info=True)
        send_custom_metric("openai_health_check", 0.0, {"status": "error"})
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/health/vertex-ai")
def health_check_vertex_ai():
    """Test Vertex AI connectivity through global GPU service"""

    try:
        if vertex_gpu_service is None:
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "vertex_ai": "unavailable",
                        "error": "VertexGPUJobService not initialized",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
                500,
            )

        # Test connectivity using the global service
        connectivity_result = vertex_gpu_service.test_vertex_ai_connectivity()

        # Send health check metric
        send_custom_metric(
            "vertex_ai_health_check",
            1.0 if connectivity_result["status"] == "healthy" else 0.0,
            {"status": connectivity_result["status"]},
        )

        if connectivity_result["status"] == "healthy":
            return jsonify(
                {
                    "status": "healthy",
                    "vertex_ai": "connected",
                    "message": connectivity_result["message"],
                    "project_id": connectivity_result["project_id"],
                    "location": connectivity_result["region"],
                    "test_job_name": connectivity_result["test_job_name"],
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        else:
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "vertex_ai": "failed",
                        "error": connectivity_result["error"],
                        "project_id": connectivity_result["project_id"],
                        "location": connectivity_result["region"],
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Vertex AI health check failed: {str(e)}", exc_info=True)
        send_custom_metric("vertex_ai_health_check", 0.0, {"status": "error"})
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "vertex_ai": "failed",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
            500,
        )


@app.get("/health/quota")
async def check_gpu_quota():
    """Check GPU quota availability across multiple regions with fallback info"""
    try:
        # Import here to avoid issues if not available
        from google.auth import default
        from googleapiclient.discovery import build

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        regions_to_check = [
            "us-central1",
            "us-west1",
            "us-east1",
            "europe-west1",
            "asia-southeast1",
        ]

        # GPU metrics to check
        gpu_metrics = ["NVIDIA_L4_GPUS", "NVIDIA_T4_GPUS"]

        creds, _ = default()
        compute = build("compute", "v1", credentials=creds, cache_discovery=False)

        quota_info = {}
        available_options = []
        cpu_options = []
        overall_status = "healthy"

        for region in regions_to_check:
            try:
                region_info = (
                    compute.regions().get(project=project_id, region=region).execute()
                )
                region_quotas = {}

                for quota in region_info.get("quotas", []):
                    metric = quota.get("metric", "")
                    if metric in gpu_metrics:
                        usage = quota.get("usage", 0)
                        limit = quota.get("limit", 0)
                        available = limit - usage

                        # Determine GPU type from metric
                        gpu_type = (
                            "L4"
                            if "L4" in metric
                            else "T4" if "T4" in metric else "Unknown"
                        )

                        region_quotas[gpu_type] = {
                            "usage": usage,
                            "limit": limit,
                            "available": available,
                        }

                        # Add to available options if quota is available (both spot and on-demand)
                        if available > 0:
                            # Use correct machine type for each GPU type from static mapping
                            from vertex_gpu_service import get_machine_type_for_gpu

                            machine_type = get_machine_type_for_gpu(
                                region, f"NVIDIA_{gpu_type}"
                            )
                            if not machine_type:
                                # Fallback to default mapping if not found
                                machine_type = (
                                    "g2-standard-8"
                                    if gpu_type == "L4"
                                    else "n1-standard-4"
                                )

                            # Add spot option first (cost optimization)
                            available_options.append(
                                {
                                    "region": region,
                                    "gpu_type": gpu_type,
                                    "available_gpus": available,
                                    "machine_type": machine_type,
                                    "spot": True,
                                    "cost_tier": "low",
                                }
                            )

                            # Add on-demand option
                            available_options.append(
                                {
                                    "region": region,
                                    "gpu_type": gpu_type,
                                    "available_gpus": available,
                                    "machine_type": machine_type,
                                    "spot": False,
                                    "cost_tier": "standard",
                                }
                            )

                # Add CPU options for each region (both spot and on-demand)
                cpu_options.extend(
                    [
                        {
                            "region": region,
                            "gpu_type": "CPU",
                            "machine_type": "n1-standard-8",
                            "spot": True,
                            "cost_tier": "low",
                            "note": "CPU fallback - high availability",
                        },
                        {
                            "region": region,
                            "gpu_type": "CPU",
                            "machine_type": "n1-standard-8",
                            "spot": False,
                            "cost_tier": "standard",
                            "note": "CPU fallback - high availability",
                        },
                    ]
                )

                quota_info[region] = region_quotas

            except Exception as e:
                logger.warning(f"Failed to get quota for region {region}: {e}")
                quota_info[region] = {"error": str(e)}

        # Determine overall status
        gpu_regions_available = len(
            set(opt["region"] for opt in available_options if opt["gpu_type"] != "CPU")
        )
        if gpu_regions_available == 0:
            overall_status = "no_gpu_quota"
        elif gpu_regions_available < 2:
            overall_status = "limited_quota"

        # Sort available options by preference (L4 > T4, spot > on-demand, us-central1 > others)
        available_options.sort(
            key=lambda x: (
                x["gpu_type"] != "L4",  # L4 first
                not x["spot"],  # Spot first for cost optimization
                x["region"] != "us-central1",  # us-central1 first
                x["region"],  # Then alphabetically
            )
        )

        # Sort CPU options by region and cost preference
        cpu_options.sort(
            key=lambda x: (
                not x["spot"],  # Spot first for cost optimization
                x["region"] != "us-central1",  # us-central1 first
                x["region"],  # Then alphabetically
            )
        )

        # Build recommendation including fallback chain
        primary_recommendation = (
            available_options[0] if available_options else cpu_options[0]
        )

        # Calculate cost savings potential
        spot_gpu_options = [opt for opt in available_options if opt["spot"]]
        cost_savings_potential = (
            len(spot_gpu_options) / max(len(available_options), 1) * 100
            if available_options
            else 0
        )

        return {
            "status": overall_status,
            "quota_details": quota_info,
            "available_gpu_options": available_options,
            "cpu_fallback_options": cpu_options,
            "recommendation": primary_recommendation,
            "fallback_chain": {
                "gpu_options": available_options,
                "cpu_options": cpu_options,
                "total_fallbacks": len(available_options) + len(cpu_options),
                "regions_covered": len(regions_to_check),
                "gpu_regions_available": gpu_regions_available,
            },
            "cost_optimization": {
                "spot_options_available": len(spot_gpu_options),
                "cost_savings_potential_percent": round(cost_savings_potential, 1),
                "estimated_cost_reduction": "60-90%" if spot_gpu_options else "0%",
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Quota check failed: {e}")
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@app.route("/health/machine-types")
def health_check_machine_types():
    """Validate GPU machine type mappings across regions"""
    try:
        if vertex_gpu_service is None:
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "error": "VertexGPUJobService not initialized",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
                500,
            )

        # Import the mapping functions
        from vertex_gpu_service import (
            REGION_GPU_MACHINE_MAP,
            discover_gpu_machine_compatibility,
        )

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        regions = [
            "us-central1",
            "us-west1",
            "us-east1",
            "europe-west1",
            "asia-southeast1",
        ]

        validation_results = {}
        overall_status = "healthy"

        for region in regions:
            try:
                # Get static mapping
                static_mapping = REGION_GPU_MACHINE_MAP.get(region, {})

                # Discover dynamic mapping
                dynamic_mapping = discover_gpu_machine_compatibility(project_id, region)

                # Compare and validate
                region_status = {
                    "static_mapping": static_mapping,
                    "dynamic_mapping": dynamic_mapping,
                    "validation": {},
                    "status": "healthy",
                }

                # Validate each GPU type
                for gpu_type in ["NVIDIA_L4", "NVIDIA_TESLA_T4", "CPU"]:
                    static_machine = static_mapping.get(gpu_type)
                    dynamic_machine = dynamic_mapping.get(gpu_type)

                    if static_machine and dynamic_machine:
                        if static_machine == dynamic_machine:
                            region_status["validation"][gpu_type] = "match"
                        else:
                            region_status["validation"][
                                gpu_type
                            ] = f"mismatch: static={static_machine}, dynamic={dynamic_machine}"
                            region_status["status"] = "warning"
                    elif dynamic_machine:
                        region_status["validation"][
                            gpu_type
                        ] = f"dynamic_only: {dynamic_machine}"
                        region_status["status"] = "info"
                    elif static_machine:
                        region_status["validation"][
                            gpu_type
                        ] = f"static_only: {static_machine}"
                        region_status["status"] = "warning"
                    else:
                        region_status["validation"][gpu_type] = "not_available"

                validation_results[region] = region_status

                if region_status["status"] == "warning":
                    overall_status = "warning"

            except Exception as e:
                validation_results[region] = {"status": "error", "error": str(e)}
                overall_status = "warning"

        return jsonify(
            {
                "status": overall_status,
                "validation_results": validation_results,
                "fallback_configs_count": len(vertex_gpu_service.fallback_configs),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Machine type validation failed: {e}")
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
            500,
        )


@app.route("/status")
def status():
    """Get the current status of video generation."""
    try:
        status_data = {
            "is_generating": is_generating,
            "is_initialized": is_initialized,
            "last_generation_time": last_generation_time,
            "last_generation_status": last_generation_status,
            "timing_metrics": timing_metrics.get_metrics(),
        }

        # Send status metrics
        send_custom_metric(
            "status_check",
            1.0,
            {
                "generating": 1.0 if is_generating else 0.0,
                "initialized": 1.0 if is_initialized else 0.0,
            },
        )

        return jsonify(status_data)
    except Exception as e:
        report_error(e, "status_check")
        return jsonify({"error": "Failed to get status"}), 500


@app.route("/generate", methods=["POST"])
def start_generation():
    """Start the video generation process."""

    try:
        if is_generating:
            send_custom_metric(
                "generation_request",
                1.0,
                {"status": "rejected", "reason": "already_generating"},
            )
            return jsonify({"error": "Video generation already in progress"}), 409

        if not is_initialized:
            send_custom_metric(
                "generation_request",
                1.0,
                {"status": "rejected", "reason": "not_initialized"},
            )
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


def generate_video_batch():
    """Run video generation once and exit (batch mode)."""
    global is_generating, last_generation_status, topic_manager, is_initialized

    logger.info("🎬 Starting AutoVideo batch processing...")

    # Initialize the application
    is_initialized = initialize_app()
    if not is_initialized:
        logger.error("❌ Application initialization failed")
        sys.exit(1)

    generation_start_time = time.time()

    try:
        is_generating = True
        # Clear old status and set to running
        last_generation_status = "generating (batch mode)"

        # Start timing
        timing_metrics.start_pipeline()

        # Send pipeline start metric
        send_custom_metric("pipeline_started", 1.0, {"mode": "batch"})
        logger.info("📊 Pipeline started - metrics sent")

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"📁 Created output directory: {output_dir}")

        # Initialize topic manager and get next topic
        if topic_manager is None:
            topic_manager = TopicManager()
        story_prompt = topic_manager.get_next_topic()
        logger.info(f"📝 Topic selected: {story_prompt}")

        # Generate content
        logger.info("🤖 Generating story...")
        last_generation_status = "generating story (batch mode)"
        timing_metrics.start_phase("story_generation")
        phase_start = time.time()
        story, prompt = generate_story(story_prompt)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "story_generation"}
        )
        logger.info(f"✅ Story generated in {phase_duration:.2f}s")

        # Extract image prompts from the story
        image_prompts = extract_image_prompts(story)
        send_custom_metric("image_prompts_count", len(image_prompts))
        logger.info(f"🖼️ Extracted {len(image_prompts)} image prompts")

        logger.info("🎨 Generating images...")
        last_generation_status = "generating images (batch mode)"
        timing_metrics.start_phase("image_generation")
        phase_start = time.time()
        image_paths = generate_images(image_prompts, output_dir)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "image_generation"}
        )
        send_custom_metric("images_generated", len(image_paths))
        logger.info(f"✅ Generated {len(image_paths)} images in {phase_duration:.2f}s")

        logger.info("🎙️ Generating voiceover...")
        last_generation_status = "generating voiceover (batch mode)"
        timing_metrics.start_phase("voiceover_generation")
        phase_start = time.time()
        audio_path = os.path.join(output_dir, "voiceover.mp3")
        generate_voiceover(story, audio_path)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "voiceover_generation"}
        )
        logger.info(f"✅ Voiceover generated in {phase_duration:.2f}s")

        # Create video using Vertex AI GPU (cloud-native - no local fallback)
        logger.info("🎬 Creating video...")
        last_generation_status = "creating video via Vertex AI (batch mode)"
        timing_metrics.start_phase("video_creation")
        phase_start = time.time()
        output_path = f"{output_dir}/final_video.mp4"

        # Use global Vertex AI GPU service (already initialized at startup)
        try:
            if vertex_gpu_service is None:
                raise Exception("VertexGPUJobService not initialized at startup")

            logger.info("🚀 Using global VertexGPUJobService for video creation...")

            # Debug: Log the paths being passed
            logger.info(f"📁 Image paths: {image_paths}")
            logger.info(f"🎵 Audio path: {audio_path}")
            logger.info(f"�� Story length: {len(story)} characters")

            # Submit job to Vertex AI
            logger.info("📤 Submitting job to Vertex AI...")
            job_id = vertex_gpu_service.create_video_job(image_paths, audio_path, story)
            logger.info(f"✅ Submitted Vertex AI job: {job_id}")

            # Update status with job ID
            last_generation_status = f"Vertex AI job running: {job_id} (batch mode)"

            # Wait for completion
            logger.info("⏳ Waiting for job completion...")
            result = vertex_gpu_service.wait_for_job_completion(job_id)

            if result.get("status") == "completed":
                # Download the result
                if vertex_gpu_service.download_video_result(job_id, output_path):
                    video_path = output_path
                    logger.info("✅ Video created successfully using Vertex AI GPU")
                    send_custom_metric(
                        "video_creation_method", 1.0, {"method": "vertex_gpu"}
                    )
                else:
                    raise Exception("Failed to download video from Vertex AI")
            else:
                raise Exception(f"Vertex AI job failed: {result}")

        except Exception as gpu_error:
            logger.error(f"❌ Vertex AI GPU processing failed: {gpu_error}")
            send_custom_metric("video_creation_method", 1.0, {"method": "failed"})
            # Cloud-native design: no local fallback, fail fast with clear error
            raise Exception(
                f"Video creation failed - Vertex AI error: {gpu_error}. This is a cloud-native app with no local processing fallback."
            )

        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "video_creation"}
        )
        logger.info(f"✅ Video created in {phase_duration:.2f}s")

        # Upload to YouTube
        logger.info("📤 Uploading to YouTube...")
        last_generation_status = "uploading to YouTube (batch mode)"
        timing_metrics.start_phase("youtube_upload")
        phase_start = time.time()
        # Extract title and description from story
        story_lines = story.split("\n")
        title = story_lines[0].replace("Title: ", "")
        description = story_lines[1].replace("Description: ", "")
        # Add the full story as additional context
        description += "\n\nFull Story:\n" + "\n".join(story_lines[2:])
        upload_video(video_path, title, description)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "youtube_upload"}
        )
        logger.info(f"✅ Video uploaded to YouTube in {phase_duration:.2f}s")

        # Calculate total pipeline duration
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric(
            "pipeline_completed", 1.0, {"status": "success", "mode": "batch"}
        )

        logger.info(
            f"🎉 Video generation and upload completed successfully in {total_duration:.2f}s"
        )
        logger.info(f"📊 Final video: {video_path}")
        last_generation_status = "completed"

        # Exit successfully
        sys.exit(0)

    except Exception as e:
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric(
            "pipeline_completed", 1.0, {"status": "error", "mode": "batch"}
        )

        report_error(e, "video_generation_pipeline_batch")
        logger.error(f"❌ Error generating video: {str(e)}")
        last_generation_status = f"error: {str(e)}"

        # Exit with error
        sys.exit(1)
    finally:
        is_generating = False
        timing_metrics.end_pipeline()
        send_custom_metric("pipeline_ended", 1.0, {"mode": "batch"})


def generate_video_thread():
    """Background thread for video generation (monitoring mode)."""
    global is_generating, last_generation_status, topic_manager

    generation_start_time = time.time()

    try:
        is_generating = True
        # Clear old status and set to running
        last_generation_status = "generating"

        # Start timing
        timing_metrics.start_pipeline()

        # Send pipeline start metric
        send_custom_metric("pipeline_started", 1.0, {"mode": "monitoring"})

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
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "story_generation"}
        )

        # Extract image prompts from the story
        image_prompts = extract_image_prompts(story)
        send_custom_metric("image_prompts_count", len(image_prompts))

        timing_metrics.start_phase("image_generation")
        phase_start = time.time()
        image_paths = generate_images(image_prompts, output_dir)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "image_generation"}
        )
        send_custom_metric("images_generated", len(image_paths))

        timing_metrics.start_phase("voiceover_generation")
        phase_start = time.time()
        audio_path = os.path.join(output_dir, "voiceover.mp3")
        generate_voiceover(story, audio_path)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "voiceover_generation"}
        )

        # Create video using Vertex AI GPU (cloud-native - no local fallback)
        logger.info("🎬 Creating video...")
        timing_metrics.start_phase("video_creation")
        phase_start = time.time()
        output_path = f"{output_dir}/final_video.mp4"

        # Update status to show current phase
        last_generation_status = "creating video via Vertex AI"

        # Use global Vertex AI GPU service (already initialized at startup)
        try:
            if vertex_gpu_service is None:
                raise Exception("VertexGPUJobService not initialized at startup")

            logger.info("🚀 Using global VertexGPUJobService for video creation...")

            # Debug: Log the paths being passed
            logger.info(f"📁 Image paths: {image_paths}")
            logger.info(f"🎵 Audio path: {audio_path}")
            logger.info(f"📝 Story length: {len(story)} characters")

            # Submit job to Vertex AI
            logger.info("📤 Submitting job to Vertex AI...")
            job_id = vertex_gpu_service.create_video_job(image_paths, audio_path, story)
            logger.info(f"✅ Submitted Vertex AI job: {job_id}")

            # Update status with job ID
            last_generation_status = f"Vertex AI job running: {job_id}"

            # Wait for completion
            logger.info("⏳ Waiting for job completion...")
            result = vertex_gpu_service.wait_for_job_completion(job_id)

            if result.get("status") == "completed":
                # Download the result
                if vertex_gpu_service.download_video_result(job_id, output_path):
                    video_path = output_path
                    logger.info("✅ Video created successfully using Vertex AI GPU")
                    send_custom_metric(
                        "video_creation_method", 1.0, {"method": "vertex_gpu"}
                    )
                else:
                    raise Exception("Failed to download video from Vertex AI")
            else:
                raise Exception(f"Vertex AI job failed: {result}")

        except Exception as gpu_error:
            logger.error(f"❌ Vertex AI GPU processing failed: {gpu_error}")
            send_custom_metric("video_creation_method", 1.0, {"method": "failed"})
            # Cloud-native design: no local fallback, fail fast with clear error
            raise Exception(
                f"Video creation failed - Vertex AI error: {gpu_error}. This is a cloud-native app with no local processing fallback."
            )

        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "video_creation"}
        )

        # Upload to YouTube
        timing_metrics.start_phase("youtube_upload")
        phase_start = time.time()
        # Update status
        last_generation_status = "uploading to YouTube"

        # Extract title and description from story
        story_lines = story.split("\n")
        title = story_lines[0].replace("Title: ", "")
        description = story_lines[1].replace("Description: ", "")
        # Add the full story as additional context
        description += "\n\nFull Story:\n" + "\n".join(story_lines[2:])
        upload_video(video_path, title, description)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "youtube_upload"}
        )

        # Calculate total pipeline duration
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric(
            "pipeline_completed", 1.0, {"status": "success", "mode": "monitoring"}
        )

        logger.info("Video generation and upload completed successfully")
        last_generation_status = "completed"

    except Exception as e:
        total_duration = time.time() - generation_start_time
        send_custom_metric("pipeline_duration", total_duration)
        send_custom_metric(
            "pipeline_completed", 1.0, {"status": "error", "mode": "monitoring"}
        )

        report_error(e, "video_generation_pipeline")
        logger.error(f"Error generating video: {str(e)}")
        last_generation_status = f"error: {str(e)}"
    finally:
        is_generating = False
        timing_metrics.end_pipeline()
        send_custom_metric("pipeline_ended", 1.0, {"mode": "monitoring"})


@app.route("/health/service-account", methods=["GET"])
def health_service_account():
    """Check runtime service account and permissions"""
    try:
        creds, project = google.auth.default()

        # Try to get service account email from metadata server (more reliable in Cloud Run)
        try:
            import requests

            metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
            headers = {"Metadata-Flavor": "Google"}
            response = requests.get(metadata_url, headers=headers, timeout=5)
            if response.status_code == 200:
                sa_email = response.text.strip()
            else:
                sa_email = getattr(creds, "service_account_email", "Unknown")
        except Exception:
            sa_email = getattr(creds, "service_account_email", "Unknown")

        return (
            jsonify(
                {
                    "status": "healthy",
                    "service_account": sa_email,
                    "project": project,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


@app.route("/health/vertex-minimal", methods=["GET"])
def health_vertex_minimal():
    """Test minimal CustomJob creation capability"""
    try:
        import google.cloud.aiplatform as aiplatform

        # Initialize aiplatform
        creds, project = google.auth.default()
        aiplatform.init(project=project, location="us-central1", credentials=creds)

        # Test minimal job creation (dry run)
        from google.cloud.aiplatform_v1 import JobServiceClient

        client = JobServiceClient(
            client_options={"api_endpoint": "us-central1-aiplatform.googleapis.com"}
        )

        # Just test the client creation and permissions - don't actually create a job
        parent = f"projects/{project}/locations/us-central1"

        # Get service account email via metadata server for accurate reporting
        try:
            import requests

            metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
            headers = {"Metadata-Flavor": "Google"}
            response = requests.get(metadata_url, headers=headers, timeout=5)
            if response.status_code == 200:
                sa_email = response.text.strip()
            else:
                sa_email = getattr(creds, "service_account_email", "Unknown")
        except Exception:
            sa_email = getattr(creds, "service_account_email", "Unknown")

        return (
            jsonify(
                {
                    "status": "healthy",
                    "message": "Vertex AI client created successfully",
                    "project": project,
                    "parent": parent,
                    "service_account": sa_email,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


# Initialize the application
try:
    is_initialized = initialize_app()
    logger.info(f"Application initialization result: {is_initialized}")

    # Check if running in Cloud Run (batch mode)
    if os.getenv("PORT") and not os.getenv("FLASK_ENV") == "development":
        logger.info("🚀 Detected Cloud Run environment - Starting BATCH mode...")
        logger.info("📋 Mode: Generate video → Upload → Exit gracefully")

        # Run batch processing in background thread to allow WSGI server to start
        # but exit after completion
        def run_batch_and_exit():
            try:
                time.sleep(2)  # Let WSGI server start
                logger.info("🎬 Starting batch video generation...")
                generate_video_batch()
            except Exception as e:
                logger.error(f"❌ Batch processing failed: {e}")
                sys.exit(1)

        batch_thread = threading.Thread(target=run_batch_and_exit)
        batch_thread.daemon = True
        batch_thread.start()

        logger.info(
            "📊 Batch processing started, WSGI server will handle health checks during generation"
        )
    else:
        logger.info(
            "📊 Running in monitoring mode - Flask server ready for manual triggers"
        )

except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    is_initialized = False

# Expose WSGI application for Gunicorn
application = app

# Create ASGI app for Hypercorn (HTTP/2 support)
try:
    from asgiref.wsgi import WsgiToAsgi

    asgi_app = WsgiToAsgi(app)
except ImportError:
    # Fallback if asgiref is not available
    asgi_app = app

# Main execution logic
if __name__ == "__main__":
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="AutoVideo Generator")
    parser.add_argument(
        "--mode",
        choices=["batch", "monitoring"],
        default="batch",
        help="Run mode: batch (generate and exit) or monitoring (keep server alive)",
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run Flask server on"
    )

    # Check if running in Cloud Run (has PORT env var)
    if os.getenv("PORT"):
        args = parser.parse_args(
            ["--mode", "batch", "--port", os.getenv("PORT", "8080")]
        )
    else:
        args = parser.parse_args()

    if args.mode == "batch":
        logger.info("🚀 Starting AutoVideo in BATCH mode...")
        logger.info("📋 Mode: Generate video → Upload → Exit gracefully")

        # Run video generation directly (not in background thread)
        generate_video_batch()

        # generate_video_batch() already calls sys.exit(), but just in case:
        logger.info("✅ Batch processing completed, exiting...")
        sys.exit(0)

    elif args.mode == "monitoring":
        logger.info("🚀 Starting AutoVideo in MONITORING mode...")
        logger.info(
            "📊 Mode: Keep Flask server alive for monitoring and manual triggers"
        )

        # Start Flask server for monitoring and manual triggers
        logger.info(f"📊 Starting Flask server on port {args.port}...")
        app.run(host="0.0.0.0", port=args.port, debug=False)
