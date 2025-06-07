# Auto Video Generator - Cloud Native
# Updated: 2025-06-07 - DEPLOYMENT TEST WITH MODIFIED GENERATE ENDPOINT
# Previous: 2025-05-28 - GPU compatibility fixes included
import json
import logging
import os
import sys
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

import google.auth
from flask import Flask, jsonify, request

# Handle Google Cloud credentials from environment variables
try:
    # Check if we have the credentials as content rather than path
    if os.environ.get("GOOGLE_CLOUD_SA_KEY"):
        # Create credentials file from environment variable
        credentials_content = os.environ.get("GOOGLE_CLOUD_SA_KEY")
        credentials_path = "/tmp/google-cloud-credentials.json"

        with open(credentials_path, "w") as f:
            f.write(credentials_content)

        # Set the credentials path environment variable
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        print(
            f"✅ Google Cloud credentials written to temporary file: {credentials_path}"
        )
except Exception as e:
    print(f"⚠️ Error setting up Google Cloud credentials: {e}")

from image_generator import generate_images
from story_generator import extract_image_prompts, generate_story, get_openai_client
from timing_metrics import TimingMetrics
from topic_manager import TopicManager
from voiceover_generator import (
    generate_elevenlabs_tts,
    generate_google_tts,
    generate_voiceover,
)
from youtube_uploader import upload_video

# Optional import for local video processing fallback
try:
    from video_creator import VEOAI_AVAILABLE, create_veo_video, create_video

    LOCAL_VIDEO_PROCESSING_AVAILABLE = True
    LOCAL_RENDER_ALLOWED = True
except ImportError as e:
    LOCAL_VIDEO_PROCESSING_AVAILABLE = False
    LOCAL_RENDER_ALLOWED = False
    logging.warning(f"Local video processing not available: {e}")
    create_video = None
    create_veo_video = None
    VEOAI_AVAILABLE = False

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

# Global variable for current render job
current_render_job_id = None

# Add these functions after the declaration of the timing_metrics variable (around line 91)


def set_current_phase(phase_name):
    """Set the current phase of video generation and update metrics."""
    global timing_metrics, current_phase  # noqa: F824 - timing_metrics is modified not assigned

    # End the previous phase if there was one
    if timing_metrics.current_phase:
        timing_metrics.end_phase()

    # Start the new phase if it's not None
    if phase_name:
        timing_metrics.start_phase(phase_name)
        current_phase = phase_name
    else:
        current_phase = None

    logger.info(f"Phase set to: {phase_name}")


def reset_timing_metrics():
    """Reset all timing metrics for a new generation."""
    global timing_metrics  # noqa: F824 - timing_metrics is modified not assigned

    # Reset the existing TimingMetrics instance instead of creating a new one
    timing_metrics.start_time = None
    timing_metrics.end_time = None
    timing_metrics.phase_times = {}
    timing_metrics.current_phase = None
    timing_metrics.phase_start_time = None
    timing_metrics.total_duration = None

    # Start the pipeline timing
    timing_metrics.start_pipeline()
    logger.info("Timing metrics reset")


def generate_video_batch():
    """Generate a video in batch mode (called from command line)."""
    logger.info("Starting batch video generation...")

    try:
        # Use the topic manager to get a topic
        topic_manager = TopicManager()
        topic = topic_manager.get_next_topic()

        logger.info(f"Selected topic: {topic}")

        # Generate the video using the same background process
        generate_video_background(topic)

        logger.info("Batch video generation completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Batch video generation failed: {str(e)}")
        sys.exit(1)


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
    """Initialize the application with all required services and clients."""
    global vertex_gpu_service, app_initialized

    try:
        # Get the current project ID
        credentials, project_id = google.auth.default()
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        logger.info(f"🔍 Application starting with project: {project_id}")

        # Validate OpenAI API key
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.warning("⚠️ OPENAI_API_KEY is missing! Story generation will fail.")
        else:
            logger.info(
                f"✅ OPENAI_API_KEY loaded successfully (length={len(openai_key)})"
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

            bucket_name = os.getenv("VERTEX_BUCKET_NAME", f"{project_id}-video-jobs")
            logger.info(f"Using bucket name: {bucket_name} for Vertex GPU service")

            vertex_gpu_service = VertexGPUJobService(
                project_id=project_id, region="us-central1", bucket_name=bucket_name
            )
            logger.info("✅ Global VertexGPUJobService initialized successfully")
        except Exception as gpu_error:
            logger.error(
                f"⚠️ Failed to initialize VertexGPUJobService: {str(gpu_error)}"
            )
            logger.error(f"⚠️ Error details: {traceback.format_exc()}")
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
    """Health check for Vertex AI connectivity."""
    result = {"status": "unknown", "details": {}}

    try:
        # Check if we have a Vertex AI client
        from google.cloud import aiplatform

        # Get project ID from environment variable or metadata server
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            try:
                import requests

                metadata_url = "http://metadata.google.internal/computeMetadata/v1/project/project-id"
                metadata_headers = {"Metadata-Flavor": "Google"}
                project_id = requests.get(
                    metadata_url, headers=metadata_headers, timeout=2
                ).text
            except Exception as e:
                result["status"] = "error"
                result["details"]["project_id_error"] = str(e)
                return jsonify(result), 500

        result["details"]["project_id"] = project_id

        # Try to initialize the client to verify service account permissions
        try:
            aiplatform.init(project=project_id, location="us-central1")
            result["details"]["client_init"] = "success"
        except Exception as e:
            result["status"] = "error"
            result["details"]["client_init_error"] = str(e)
            return jsonify(result), 500

        # Test the simplest possible API call to verify service account permissions
        try:
            response = aiplatform.Model.list(filter="display_name=bert-base")
            result["details"]["api_call"] = "success"
            result["details"]["api_response"] = "Got response with {} models".format(
                len(response)
            )
        except Exception as e:
            result["status"] = "error"
            result["details"]["api_call_error"] = str(e)
            return jsonify(result), 500

        result["status"] = "healthy"
        return jsonify(result)

    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
        return jsonify(result), 500


@app.route("/health/veo")
def health_check_veo():
    """Health check for Veo API connectivity."""
    result = {"status": "unknown", "details": {}}

    try:
        # Check if the Veo module is available
        if not VEOAI_AVAILABLE:
            result["status"] = "unavailable"
            result["details"]["error"] = "Veo SDK not installed"
            return jsonify(result), 503

        # Try to initialize the Veo model to verify permissions
        try:
            from vertexai.preview.generative_models import GenerativeModel

            # Just attempt to load the model (won't make an API call yet)
            model = GenerativeModel("veo-3")
            result["details"]["model_init"] = "success"

            # Try to list available models to check API connectivity
            from vertexai.preview import models

            # Check if the model exists in the list
            try:
                model_list = [m.name for m in models.list_models()]
                if "veo-3" in model_list or any("veo" in m.lower() for m in model_list):
                    result["details"]["model_exists"] = True
                    result["details"]["available_models"] = [
                        m for m in model_list if "veo" in m.lower()
                    ]
                else:
                    result["details"]["model_exists"] = False
                    result["details"]["note"] = "Veo models not found in model list"
            except Exception as e:
                result["details"]["model_list_error"] = str(e)
                # Continue with health check even if model listing fails

            # For a more thorough check, we could generate a tiny test video
            # but that would consume quota, so we'll skip it for health checks

            result["status"] = "healthy"
            return jsonify(result)

        except Exception as e:
            result["status"] = "error"
            result["details"]["model_init_error"] = str(e)
            return jsonify(result), 500

    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
        return jsonify(result), 500


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


def get_vertex_ai_job_details(job_id: str) -> Dict[str, Any]:
    """Get detailed status information for a Vertex AI job"""
    try:
        if not job_id or vertex_gpu_service is None:
            return None

        # Extract just the job ID without prefix text
        if "job running:" in job_id:
            job_id = job_id.split("job running: ")[1].split(" ")[0]
        elif "Vertex AI job running:" in job_id:
            job_id = job_id.split("Vertex AI job running: ")[1].split(" ")[0]

        # Use gcloud CLI to get job details since it's more reliable
        import json
        import subprocess

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        region = "us-central1"

        # Find the actual job by display name pattern
        cmd = [
            "gcloud",
            "ai",
            "custom-jobs",
            "list",
            f"--region={region}",
            f"--project={project_id}",
            f"--filter=displayName:av-video-render-{job_id}",
            "--limit=1",
            "--format=json",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0 and result.stdout.strip():
            jobs = json.loads(result.stdout)
            if jobs:
                job = jobs[0]

                # Parse timestamps
                create_time = job.get("createTime", "")
                start_time = job.get("startTime", "")
                end_time = job.get("endTime", "")

                # Calculate duration
                duration_info = {}
                if create_time and start_time:
                    create_dt = datetime.fromisoformat(
                        create_time.replace("Z", "+00:00")
                    )
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    queue_duration = (start_dt - create_dt).total_seconds()
                    duration_info["queue_duration"] = queue_duration

                if start_time:
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    if end_time:
                        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        run_duration = (end_dt - start_dt).total_seconds()
                        duration_info["run_duration"] = run_duration
                        duration_info["total_duration"] = (
                            queue_duration + run_duration
                            if "queue_duration" in duration_info
                            else run_duration
                        )
                    else:
                        # Still running
                        current_time = datetime.utcnow()
                        run_duration = (
                            current_time - start_dt.replace(tzinfo=None)
                        ).total_seconds()
                        duration_info["run_duration"] = run_duration
                        if "queue_duration" in duration_info:
                            duration_info["total_duration"] = (
                                queue_duration + run_duration
                            )

                # Extract machine type and GPU info
                worker_pool = job.get("jobSpec", {}).get("workerPoolSpecs", [{}])[0]
                machine_spec = worker_pool.get("machineSpec", {})
                machine_type = machine_spec.get("machineType", "unknown")
                accelerator_type = machine_spec.get("acceleratorType", "")
                accelerator_count = machine_spec.get("acceleratorCount", 0)

                # Get region from labels
                labels = job.get("labels", {})
                region = labels.get("region", "unknown").replace("_", "-")

                return {
                    "job_id": job_id,
                    "display_name": job.get("displayName", ""),
                    "state": job.get("state", "UNKNOWN"),
                    "region": region,
                    "machine_type": machine_type,
                    "accelerator_type": accelerator_type,
                    "accelerator_count": accelerator_count,
                    "create_time": create_time,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration_info,
                    "resource_name": job.get("name", ""),
                    "error": (
                        job.get("error", {}).get("message", "")
                        if job.get("error")
                        else None
                    ),
                }

        return None

    except Exception as e:
        logger.warning(f"Failed to get Vertex AI job details for {job_id}: {e}")
        return None


@app.route("/status")
def status():
    """Get the current status of video generation with enhanced Vertex AI job details."""
    try:
        # Basic status data
        status_data = {
            "is_generating": is_generating,
            "is_initialized": is_initialized,
            "last_generation_time": last_generation_time,
            "last_generation_status": last_generation_status,
            "timing_metrics": timing_metrics.get_metrics(),
        }

        # Add Vertex AI job details if available
        vertex_job_details = None
        if (
            is_generating
            and last_generation_status
            and "job" in last_generation_status.lower()
        ):
            vertex_job_details = get_vertex_ai_job_details(last_generation_status)

        if vertex_job_details:
            status_data["vertex_ai_job"] = vertex_job_details

            # Enhance the status message with job state
            job_state = vertex_job_details.get("state", "UNKNOWN")
            job_id = vertex_job_details.get("job_id", "unknown")
            region = vertex_job_details.get("region", "unknown")
            machine_info = vertex_job_details.get("machine_type", "unknown")

            if vertex_job_details.get("accelerator_type"):
                gpu_info = f"{vertex_job_details.get('accelerator_count', 1)}x {vertex_job_details.get('accelerator_type', '')}"
                machine_info += f" + {gpu_info}"

            # Format duration info
            duration_info = vertex_job_details.get("duration", {})
            duration_text = ""
            if "total_duration" in duration_info:
                total_mins = duration_info["total_duration"] / 60
                duration_text = f" ({total_mins:.1f}m total)"
            elif "run_duration" in duration_info:
                run_mins = duration_info["run_duration"] / 60
                duration_text = f" ({run_mins:.1f}m running)"
            elif "queue_duration" in duration_info:
                queue_mins = duration_info["queue_duration"] / 60
                duration_text = f" ({queue_mins:.1f}m queued)"

            # Enhanced status message
            status_data["enhanced_status"] = (
                f"Vertex AI {job_state}: {job_id} on {machine_info} in {region}{duration_text}"
            )

            # Add error information if job failed
            if vertex_job_details.get("error"):
                status_data["error"] = vertex_job_details["error"]

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


@app.route("/cancel", methods=["POST"])
def cancel_generation():
    """Cancel the current video generation process."""
    global is_generating, is_initialized, video_file_path, current_phase

    logger.info("🚫 Canceling current generation process...")

    # Reset all the global flags
    is_generating = False
    is_initialized = False
    video_file_path = None
    current_phase = None

    # Reset timing metrics
    reset_timing_metrics()

    return jsonify({"success": True, "message": "Video generation canceled"})


@app.route("/generate", methods=["POST"])
def start_generation():
    """Start the video generation process."""
    global is_generating, is_initialized, last_generation_status, last_generation_time

    try:
        if is_generating:
            return jsonify({"error": "Video generation is already in progress"}), 400

        # Get request data
        data = request.json or {}

        # Start a background thread for the video generation
        topic = data.get("topic", "The future of technology")
        logger.info(f"🚀 Starting video generation for topic: '{topic}'")

        # Update global state
        is_generating = True
        is_initialized = True
        last_generation_status = "initializing"
        last_generation_time = datetime.now()

        # Reset timing metrics
        reset_timing_metrics()

        # Start the generation in a background thread
        thread = threading.Thread(target=generate_video_background, args=(topic,))
        thread.daemon = True
        thread.start()

        # Send custom metric for generation start
        send_custom_metric("pipeline_started", 1.0)

        return jsonify(
            {
                "status": "started",
                "topic": topic,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        report_error(e, "start_generation")
        return jsonify({"error": f"Failed to start video generation: {str(e)}"}), 500


def generate_video_background(topic):
    """Background thread for video generation process."""
    global is_generating, last_generation_status, last_generation_time, video_file_path

    try:
        # Set up timing metrics
        start_time = time.time()
        set_current_phase("story_generation")

        logger.info(f"Generating story for topic: {topic}")
        story, _ = generate_story(f"Write a story about {topic}", timeout=60)

        # Extract image prompts
        set_current_phase("prompt_extraction")
        logger.info("Extracting image prompts from story")
        image_prompts = extract_image_prompts(story, num_scenes=5)

        # Generate images
        set_current_phase("image_generation")
        logger.info(f"Generating {len(image_prompts)} images")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)

        image_paths = generate_images(image_prompts, f"{output_dir}/images")

        # Generate voiceover
        set_current_phase("voiceover_generation")
        logger.info("Generating voiceover")
        audio_path = f"{output_dir}/audio.mp3"

        try:
            # First try ElevenLabs
            audio_path = generate_elevenlabs_tts(story, audio_path)
            logger.info("Generated voiceover using ElevenLabs")
        except Exception as e:
            # Fall back to Google TTS
            logger.warning(
                f"ElevenLabs TTS failed, falling back to Google TTS: {str(e)}"
            )
            audio_path = generate_google_tts(story, audio_path)
            logger.info("Generated voiceover using Google TTS fallback")

        # Create video
        set_current_phase("video_creation")
        logger.info("Creating video")
        video_path = f"{output_dir}/video.mp4"

        # Try Veo video generation first if available
        if VEOAI_AVAILABLE and create_veo_video:
            logger.info("Attempting to create video with Veo AI")
            try:
                video_file_path = create_veo_video(story, video_path, num_scenes=5)
                logger.info(f"Veo video created successfully: {video_file_path}")
            except Exception as veo_error:
                logger.error(f"Veo video creation failed: {str(veo_error)}")
                logger.info("Falling back to other video creation methods")
                video_file_path = None
        else:
            logger.info("Veo AI not available, trying alternative methods")
            video_file_path = None

        # If Veo failed, use local video processing if available
        if (
            video_file_path is None
            and LOCAL_VIDEO_PROCESSING_AVAILABLE
            and LOCAL_RENDER_ALLOWED
            and create_video
        ):
            logger.info("Creating video using local processing")
            try:
                video_file_path = create_video(
                    image_paths, audio_path, story, timestamp, video_path
                )
                logger.info(
                    f"Video created successfully with local processing: {video_file_path}"
                )
            except Exception as local_error:
                logger.error(f"Local video processing failed: {str(local_error)}")
                video_file_path = None

        # If both Veo and local processing failed, try Vertex AI GPU service as last resort
        if video_file_path is None and vertex_gpu_service is not None:
            logger.info("Trying Vertex AI GPU service as last resort")
            try:
                job_id = vertex_gpu_service.create_video_job(
                    image_paths, audio_path, story
                )
                logger.info(f"Submitted Vertex AI GPU job with ID: {job_id}")

                # Wait for job completion with timeout
                status = vertex_gpu_service.wait_for_job_completion(job_id, timeout=600)

                if status.get("status") == "completed":
                    # Download the video result
                    logger.info(f"GPU job completed successfully, downloading video")
                    if vertex_gpu_service.download_video_result(job_id, video_path):
                        video_file_path = video_path
                        logger.info(f"Video downloaded successfully: {video_file_path}")
                    else:
                        raise Exception("Failed to download video from GPU job")
                else:
                    raise Exception(
                        f"GPU job failed with status: {status.get('status')}"
                    )

            except Exception as gpu_error:
                logger.error(f"Vertex AI GPU video creation failed: {str(gpu_error)}")
                raise Exception(
                    f"Video creation failed: GPU processing error - {str(gpu_error)}"
                )

        # If we still don't have a video, all methods failed
        if video_file_path is None:
            logger.error("All video creation methods failed")
            raise Exception("Video creation failed: no video processing available")

        # Update status
        last_generation_status = "completed"
        last_generation_time = datetime.now()

        # Record completion metric
        total_duration = time.time() - start_time
        send_custom_metric("pipeline_completed", 1.0, {"status": "success"})
        send_custom_metric("pipeline_duration", total_duration)

        logger.info(f"✅ Video generation completed in {total_duration:.2f} seconds")

    except Exception as e:
        logger.error(f"❌ Video generation failed: {str(e)}")
        last_generation_status = f"error: {str(e)}"
        last_generation_time = datetime.now()
        send_custom_metric("pipeline_completed", 0.0, {"status": "error"})

    finally:
        # Reset the generation flag
        is_generating = False
        set_current_phase(None)


@app.route("/reset", methods=["POST"])
def reset():
    """Reset the generation state for debugging purposes"""
    global is_generating, last_generation_status, last_generation_time

    # Reset state variables
    is_generating = False
    last_generation_status = "reset"
    last_generation_time = None

    # Reset timing metrics
    reset_timing_metrics()

    return jsonify({"status": "success", "message": "Generation state reset"})


@app.route("/debug", methods=["GET"])
def debug_endpoint():
    """Debug endpoint to check deployment status."""
    return jsonify(
        {
            "deployment_timestamp": "2025-06-07T18:15",
            "generate_endpoint_implemented": True,
            "commit_message": "Add deployment test comment to confirm code changes are being deployed",
        }
    )


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

# Deployment command:
#
# gcloud run deploy av-app \
#   --region=us-central1 \
#   --image=gcr.io/av-8675309/av-app:latest \
#   --platform=managed \
#   --memory=8Gi \
#   --cpu=4 \
#   --concurrency=10 \
#   --timeout=3600 \
#   --min-instances=1 \
#   --set-env-vars="OPENAI_API_KEY=${OPENAI_API_KEY},ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY},LOCAL_RENDER_ALLOWED=true,LOCAL_VIDEO_PROCESSING_AVAILABLE=true,VEO_ENABLED=true" \
#   --service-account=service-939407899550@gcp-sa-aiplatform-cc.iam.gserviceaccount.com
