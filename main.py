# Auto Video Generator - Cloud Native
# Updated: 2025-05-28 - GPU compatibility fixes included
import json
import logging
import os
import sys
import threading
import time
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
from voiceover_generator import generate_voiceover, generate_google_tts, generate_elevenlabs_tts
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

# Global variable for current render job
current_render_job_id = None


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

        # Get request parameters
        request_data = request.get_json() or {}
        topic = request_data.get("topic")
        max_length = request_data.get("max_length")
        tts_service = request_data.get("tts_service", "elevenlabs")  # Default to elevenlabs
        
        # Log the generation request parameters
        logger.info(f"🎬 Video generation requested - Topic: {topic}, TTS: {tts_service}")
        
        # Send generation start metric
        send_custom_metric("generation_request", 1.0, {"status": "accepted"})
        send_custom_metric("generation_started", 1.0, {"trigger": "manual_api"})

        # Start video generation in a background thread
        thread = threading.Thread(
            target=generate_video_thread,
            kwargs={"tts_service": tts_service, "topic": topic, "max_length": max_length}
        )
        thread.daemon = True
        thread.start()

        return jsonify({"status": "started", "message": "Video generation started"})

    except Exception as e:
        report_error(e, "start_generation")
        send_custom_metric("generation_request", 1.0, {"status": "error"})
        return jsonify({"error": "Failed to start generation"}), 500


@app.route("/render-fallback", methods=["POST"])
def trigger_fast_render_fallback():
    """
    Trigger fast VM-based render fallback when Vertex AI is too slow
    """
    global last_generation_status

    try:
        # Get video length from request or use default
        video_length = request.json.get("video_length_s", 180) if request.json else 180

        # Update status
        last_generation_status = "launching fast render VM"

        # Launch the fast render VM
        logger.info("🚀 Triggering fast render fallback...")

        import os
        import subprocess

        # Set environment variables for the script
        env = os.environ.copy()
        env["VIDEO_LENGTH_S"] = str(video_length)

        # Launch the fast render script
        result = subprocess.run(
            ["python3", "scripts/launch_fast_render.py"],
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode == 0:
            last_generation_status = "fast render VM launched successfully"
            logger.info("✅ Fast render VM launched successfully")

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Fast render VM launched successfully",
                        "output": result.stdout,
                    }
                ),
                200,
            )
        else:
            last_generation_status = f"fast render launch failed: {result.stderr}"
            logger.error(f"❌ Fast render launch failed: {result.stderr}")

            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Failed to launch fast render VM",
                        "error": result.stderr,
                    }
                ),
                500,
            )

    except Exception as e:
        last_generation_status = f"fast render error: {str(e)}"
        logger.error(f"❌ Fast render fallback error: {e}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Fast render fallback failed",
                    "error": str(e),
                }
            ),
            500,
        )


def check_vm_render_status():
    """
    Check status of any running render VMs
    """
    try:
        import subprocess

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")

        # List any running render VMs
        result = subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "list",
                f"--project={project_id}",
                "--filter=name~av-render-* AND status:RUNNING",
                "--format=json",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            import json

            vms = json.loads(result.stdout)
            return {
                "vm_count": len(vms),
                "vms": [
                    {"name": vm["name"], "status": vm["status"], "zone": vm["zone"]}
                    for vm in vms
                ],
            }
        else:
            return {"error": "Failed to check VM status", "details": result.stderr}

    except Exception as e:
        return {"error": f"VM status check failed: {e}"}


@app.route("/vm-status", methods=["GET"])
def vm_status():
    """Check status of running render VMs"""
    try:
        vm_info = check_vm_render_status()
        return jsonify(vm_info), 200
    except Exception as e:
        return jsonify({"error": f"Failed to check VM status: {e}"}), 500


def stage_assets_for_vm_render(image_paths, audio_path, story, output_dir):
    """
    Stage generated assets to Cloud Storage for VM access
    """
    try:
        import json
        import uuid

        from google.cloud import storage

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        staging_bucket_name = f"{project_id}-staging"

        # Initialize storage client
        storage_client = storage.Client()

        # Create bucket if it doesn't exist
        try:
            bucket = storage_client.bucket(staging_bucket_name)
            bucket.reload()  # Check if bucket exists
        except Exception:
            logger.info(f"Creating staging bucket: {staging_bucket_name}")
            bucket = storage_client.create_bucket(staging_bucket_name)

        # Generate unique job ID for this render
        job_id = str(uuid.uuid4())[:8]

        # Upload assets
        logger.info(f"📦 Staging assets for job {job_id}...")

        # Upload images
        image_urls = []
        for i, image_path in enumerate(image_paths):
            blob_name = f"jobs/{job_id}/images/image_{i:03d}.jpg"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(image_path)
            image_urls.append(f"gs://{staging_bucket_name}/{blob_name}")

        # Upload audio
        audio_blob_name = f"jobs/{job_id}/audio/voiceover.mp3"
        audio_blob = bucket.blob(audio_blob_name)
        audio_blob.upload_from_filename(audio_path)
        audio_url = f"gs://{staging_bucket_name}/{audio_blob_name}"

        # Upload story as JSON
        story_data = {
            "story": story,
            "job_id": job_id,
            "timestamp": datetime.now().isoformat(),
            "image_urls": image_urls,
            "audio_url": audio_url,
        }

        story_blob_name = f"jobs/{job_id}/story.json"
        story_blob = bucket.blob(story_blob_name)
        story_blob.upload_from_string(
            json.dumps(story_data), content_type="application/json"
        )

        # Upload job metadata
        metadata = {
            "job_id": job_id,
            "assets_staged": True,
            "image_count": len(image_paths),
            "story_blob": f"gs://{staging_bucket_name}/{story_blob_name}",
            "output_dir": output_dir,
        }

        metadata_blob_name = f"jobs/{job_id}/metadata.json"
        metadata_blob = bucket.blob(metadata_blob_name)
        metadata_blob.upload_from_string(
            json.dumps(metadata), content_type="application/json"
        )

        logger.info(f"✅ Assets staged successfully for job {job_id}")

        # Store job ID globally for VM to access
        global current_render_job_id
        current_render_job_id = job_id

        return True

    except Exception as e:
        logger.error(f"❌ Failed to stage assets: {e}")
        return False


def launch_fast_render_vm(video_length_s=180):
    """
    Launch fast render VM using the existing script
    """
    try:
        import os
        import subprocess

        # Set environment variables
        env = os.environ.copy()
        env["VIDEO_LENGTH_S"] = str(video_length_s)
        env["RENDER_JOB_ID"] = current_render_job_id or "unknown"

        # Launch the fast render script
        result = subprocess.run(
            ["python3", "scripts/launch_fast_render.py"],
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode == 0:
            # Extract VM name from output
            output_lines = result.stdout.split("\n")
            vm_name = None
            for line in output_lines:
                if "Fast render VM" in line and "is starting up" in line:
                    # Extract VM name from: "Fast render VM 'av-render-abc123' is starting up!"
                    vm_name = line.split("'")[1]
                    break

            return {
                "success": True,
                "vm_name": vm_name or "unknown",
                "output": result.stdout,
            }
        else:
            return {"success": False, "error": result.stderr, "output": result.stdout}

    except Exception as e:
        return {"success": False, "error": str(e)}


def wait_for_vm_completion(vm_name, expected_output_path, timeout=7200):
    """
    Wait for VM to complete and download the result
    """
    try:
        import time

        from google.cloud import storage

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        output_bucket_name = f"{project_id}-outputs"

        storage_client = storage.Client()
        bucket = storage_client.bucket(output_bucket_name)

        start_time = time.time()
        check_interval = 30  # Check every 30 seconds

        logger.info(f"⏳ Waiting for VM {vm_name} to complete (timeout: {timeout}s)...")

        while time.time() - start_time < timeout:
            # Check if VM still exists and is running
            vm_status = check_vm_instance_status(vm_name)

            if vm_status == "TERMINATED":
                logger.info(f"✅ VM {vm_name} has terminated - checking for output...")

                # Look for output file in the bucket
                # VM uploads to renders/{timestamp}-video.mp4
                blobs = bucket.list_blobs(prefix="renders/")

                # Find most recent blob (VM should have just created it)
                recent_blobs = []
                cutoff_time = start_time - 300  # 5 minutes before we started waiting

                for blob in blobs:
                    if (
                        blob.name.endswith(".mp4")
                        and blob.time_created.timestamp() > cutoff_time
                    ):
                        recent_blobs.append(blob)

                if recent_blobs:
                    # Get the most recent one
                    latest_blob = max(recent_blobs, key=lambda b: b.time_created)

                    # Download it to expected location
                    logger.info(f"📥 Downloading result from {latest_blob.name}...")
                    latest_blob.download_to_filename(expected_output_path)

                    logger.info(
                        f"✅ Video downloaded successfully to {expected_output_path}"
                    )
                    return expected_output_path
                else:
                    logger.error("❌ VM terminated but no output file found")
                    return None

            elif vm_status == "ERROR" or vm_status is None:
                logger.error(f"❌ VM {vm_name} failed or not found")
                return None

            # Still running, wait and check again
            time.sleep(check_interval)
            elapsed = time.time() - start_time
            logger.info(f"⏳ VM still running... ({elapsed/60:.1f}m elapsed)")

        # Timeout reached
        logger.error(f"❌ VM {vm_name} timed out after {timeout}s")
        return None

    except Exception as e:
        logger.error(f"❌ Error waiting for VM completion: {e}")
        return None


def check_vm_instance_status(vm_name):
    """
    Check the status of a specific VM instance
    """
    try:
        import subprocess

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")

        result = subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "describe",
                vm_name,
                f"--project={project_id}",
                "--zone=us-central1-a",
                "--format=value(status)",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return None

    except Exception as e:
        logger.error(f"Failed to check VM status: {e}")
        return None


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
            logger.info(f"📝 Story length: {len(story)} characters")

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

            # Check if this is a timeout or failure that could benefit from fast render fallback
            error_str = str(gpu_error).lower()
            is_timeout = any(
                keyword in error_str for keyword in ["timeout", "time", "3600", "hour"]
            )
            is_quota_issue = any(
                keyword in error_str for keyword in ["quota", "limit", "exceeded"]
            )

            if is_timeout or is_quota_issue:
                logger.info(
                    "🚀 Vertex AI failed due to timeout/quota - attempting fast render fallback..."
                )

                try:
                    # Stage assets to Cloud Storage for VM access
                    staging_success = stage_assets_for_vm_render(
                        image_paths, audio_path, story, output_dir
                    )

                    if staging_success:
                        # Launch fast render VM
                        vm_result = launch_fast_render_vm(video_length_s=180)

                        if vm_result.get("success"):
                            logger.info(
                                "✅ Fast render VM launched - monitoring for completion..."
                            )
                            last_generation_status = (
                                f"fast render VM active: {vm_result['vm_name']}"
                            )

                            # Wait for VM completion (with reasonable timeout)
                            vm_video_path = wait_for_vm_completion(
                                vm_result["vm_name"], output_path, timeout=7200
                            )  # 2 hours

                            if vm_video_path:
                                video_path = vm_video_path
                                logger.info(
                                    "✅ Video created successfully using fast render VM"
                                )
                                send_custom_metric(
                                    "video_creation_method",
                                    1.0,
                                    {"method": "fast_render_vm"},
                                )
                            else:
                                raise Exception("Fast render VM failed to complete")
                        else:
                            raise Exception(
                                f"Failed to launch fast render VM: {vm_result.get('error')}"
                            )
                    else:
                        raise Exception("Failed to stage assets for VM render")

                except Exception as fallback_error:
                    logger.error(
                        f"❌ Fast render fallback also failed: {fallback_error}"
                    )
                    # Cloud-native design: no local fallback, fail fast with clear error
                    raise Exception(
                        f"Video creation failed - Vertex AI error: {gpu_error}. Fast render fallback also failed: {fallback_error}. This is a cloud-native app with no local processing fallback."
                    )
            else:
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


def generate_video_thread(tts_service="elevenlabs", topic=None, max_length=None):
    """
    Background thread for video generation (monitoring mode).
    
    Args:
        tts_service (str): Text-to-speech service to use: "elevenlabs" or "google"
        topic (str): Optional topic for the video
        max_length (int): Optional maximum length for the story
    """
    global is_generating, last_generation_status, topic_manager

    generation_start_time = time.time()

    try:
        is_generating = True
        # Clear old status and set to running
        last_generation_status = "generating"
        
        # Log generation parameters
        logger.info(f"🚀 Starting video generation - TTS: {tts_service}, Topic: {topic}")

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
            
        # Use specified topic if provided, otherwise get one from topic manager
        if topic:
            story_prompt = topic
            logger.info(f"📝 Using provided topic: {story_prompt}")
        else:
            story_prompt = topic_manager.get_next_topic()
            logger.info(f"📝 Using generated topic: {story_prompt}")

        # Generate content
        timing_metrics.start_phase("story_generation")
        phase_start = time.time()
        story, prompt = generate_story(story_prompt, max_length=max_length)
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

        # Update status to show voiceover generation with TTS service
        last_generation_status = f"generating voiceover using {tts_service}"
        logger.info(f"🎙️ Generating voiceover using {tts_service} service...")
        
        timing_metrics.start_phase("voiceover_generation")
        phase_start = time.time()
        audio_path = os.path.join(output_dir, "voiceover.mp3")
        generate_voiceover(story, audio_path, tts_service=tts_service)
        phase_duration = time.time() - phase_start
        timing_metrics.end_phase()
        send_custom_metric(
            "phase_duration", phase_duration, {"phase": "voiceover_generation"}
        )
        logger.info(f"✅ Voiceover generation completed in {phase_duration:.2f}s")

        # Create video using Vertex AI GPU (cloud-native - no local fallback)
        logger.info("🎬 Creating video...")
        timing_metrics.start_phase("video_creation")
        phase_start = time.time()
        output_path = f"{output_dir}/final_video.mp4"

        # Update status with job ID
        last_generation_status = f"Vertex AI job running: {job_id}"

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

            # Check if this is a timeout or failure that could benefit from fast render fallback
            error_str = str(gpu_error).lower()
            is_timeout = any(
                keyword in error_str for keyword in ["timeout", "time", "3600", "hour"]
            )
            is_quota_issue = any(
                keyword in error_str for keyword in ["quota", "limit", "exceeded"]
            )

            if is_timeout or is_quota_issue:
                logger.info(
                    "🚀 Vertex AI failed due to timeout/quota - attempting fast render fallback..."
                )

                try:
                    # Stage assets to Cloud Storage for VM access
                    staging_success = stage_assets_for_vm_render(
                        image_paths, audio_path, story, output_dir
                    )

                    if staging_success:
                        # Launch fast render VM
                        vm_result = launch_fast_render_vm(video_length_s=180)

                        if vm_result.get("success"):
                            logger.info(
                                "✅ Fast render VM launched - monitoring for completion..."
                            )
                            last_generation_status = (
                                f"fast render VM active: {vm_result['vm_name']}"
                            )

                            # Wait for VM completion (with reasonable timeout)
                            vm_video_path = wait_for_vm_completion(
                                vm_result["vm_name"], output_path, timeout=7200
                            )  # 2 hours

                            if vm_video_path:
                                video_path = vm_video_path
                                logger.info(
                                    "✅ Video created successfully using fast render VM"
                                )
                                send_custom_metric(
                                    "video_creation_method",
                                    1.0,
                                    {"method": "fast_render_vm"},
                                )
                            else:
                                raise Exception("Fast render VM failed to complete")
                        else:
                            raise Exception(
                                f"Failed to launch fast render VM: {vm_result.get('error')}"
                            )
                    else:
                        raise Exception("Failed to stage assets for VM render")

                except Exception as fallback_error:
                    logger.error(
                        f"❌ Fast render fallback also failed: {fallback_error}"
                    )
                    # Cloud-native design: no local fallback, fail fast with clear error
                    raise Exception(
                        f"Video creation failed - Vertex AI error: {gpu_error}. Fast render fallback also failed: {fallback_error}. This is a cloud-native app with no local processing fallback."
                    )
            else:
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


@app.route("/health/tts", methods=["GET"])
def check_tts_health():
    """
    Check the health of TTS services and report detailed status.
    This endpoint is useful for troubleshooting TTS failures.
    """
    try:
        result = {
            "status": "checking",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "elevenlabs": {
                    "configured": bool(os.getenv("ELEVENLABS_API_KEY")),
                    "status": "unknown",
                },
                "google_tts": {
                    "configured": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
                    "status": "unknown",
                    "credentials_path": os.getenv(
                        "GOOGLE_APPLICATION_CREDENTIALS", "not set"
                    ),
                },
            },
        }

        # Check ElevenLabs if configured
        if result["services"]["elevenlabs"]["configured"]:
            try:
                # Simple auth check with ElevenLabs API
                import requests

                api_key = os.getenv("ELEVENLABS_API_KEY")
                headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
                response = requests.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers=headers,
                    timeout=10,
                )

                if response.status_code == 200:
                    user_data = response.json()
                    result["services"]["elevenlabs"]["status"] = "healthy"
                    result["services"]["elevenlabs"]["quota"] = {
                        "character_count": user_data.get("character_count", 0),
                        "character_limit": user_data.get("character_limit", 0),
                        "remaining_characters": user_data.get("character_limit", 0)
                        - user_data.get("character_count", 0),
                    }
                else:
                    result["services"]["elevenlabs"]["status"] = "error"
                    result["services"]["elevenlabs"][
                        "error"
                    ] = f"HTTP {response.status_code}: {response.text}"
            except Exception as e:
                result["services"]["elevenlabs"]["status"] = "error"
                result["services"]["elevenlabs"]["error"] = str(e)

        # Check Google Cloud TTS if configured
        if result["services"]["google_tts"]["configured"]:
            try:
                from google.cloud import texttospeech

                client = texttospeech.TextToSpeechClient()

                # List available voices (lightweight API call)
                voices = client.list_voices()
                result["services"]["google_tts"]["status"] = "healthy"
                result["services"]["google_tts"]["voices_available"] = len(
                    voices.voices
                )
            except Exception as e:
                result["services"]["google_tts"]["status"] = "error"
                result["services"]["google_tts"]["error"] = str(e)

        # Determine overall health
        if (
            result["services"]["elevenlabs"]["status"] == "healthy"
            or result["services"]["google_tts"]["status"] == "healthy"
        ):
            result["status"] = "healthy"
        elif (
            result["services"]["elevenlabs"]["configured"]
            and result["services"]["google_tts"]["configured"]
        ):
            result["status"] = "critical"
        else:
            result["status"] = "degraded"

        return jsonify(result)
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


@app.route("/health/tts/test", methods=["GET"])
def test_tts_services():
    """
    Test both TTS services directly and provide detailed diagnostic information.
    This endpoint will actually attempt to generate audio with both services.
    """
    test_results = {
        "timestamp": datetime.now().isoformat(),
        "status": "testing",
        "services": {
            "elevenlabs": {"status": "untested"},
            "google_tts": {"status": "untested"},
        },
    }

    test_text = "This is a test of the text to speech system."
    
    # Test Google TTS first (as it's more reliable generally)
    try:
        from voiceover_generator import generate_google_tts
        
        logger.info("🔄 Testing Google Cloud TTS...")
        test_results["services"]["google_tts"]["status"] = "testing"
        
        # Create a temporary file for the test audio
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_file.close()
        
        start_time = time.time()
        generate_google_tts(test_text, temp_file.name)
        duration = time.time() - start_time
        
        # Check if file was created and has content
        if os.path.exists(temp_file.name) and os.path.getsize(temp_file.name) > 0:
            test_results["services"]["google_tts"] = {
                "status": "healthy",
                "duration_seconds": round(duration, 2),
                "file_size_bytes": os.path.getsize(temp_file.name),
                "credentials_path": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "not set"),
            }
            logger.info(f"✅ Google TTS test successful in {duration:.2f}s")
        else:
            test_results["services"]["google_tts"] = {
                "status": "error",
                "error": "Generated file is empty or missing",
                "duration_seconds": round(duration, 2),
            }
            
        # Clean up the temporary file
        try:
            os.unlink(temp_file.name)
        except:
            pass
            
    except Exception as e:
        test_results["services"]["google_tts"] = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.error(f"❌ Google TTS test failed: {str(e)}")
    
    # Now test ElevenLabs
    try:
        from voiceover_generator import generate_elevenlabs_tts
        
        # Skip if no API key is configured
        if not os.getenv("ELEVENLABS_API_KEY"):
            test_results["services"]["elevenlabs"] = {
                "status": "skipped",
                "reason": "No API key configured"
            }
        else:
            logger.info("🔄 Testing ElevenLabs TTS...")
            test_results["services"]["elevenlabs"]["status"] = "testing"
            
            # Create a temporary file for the test audio
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_file.close()
            
            start_time = time.time()
            try:
                generate_elevenlabs_tts(test_text, temp_file.name)
                duration = time.time() - start_time
                
                # Check if file was created and has content
                if os.path.exists(temp_file.name) and os.path.getsize(temp_file.name) > 0:
                    test_results["services"]["elevenlabs"] = {
                        "status": "healthy",
                        "duration_seconds": round(duration, 2),
                        "file_size_bytes": os.path.getsize(temp_file.name),
                    }
                    logger.info(f"✅ ElevenLabs test successful in {duration:.2f}s")
                else:
                    test_results["services"]["elevenlabs"] = {
                        "status": "error",
                        "error": "Generated file is empty or missing",
                        "duration_seconds": round(duration, 2),
                    }
            except Exception as elevenlabs_error:
                duration = time.time() - start_time
                test_results["services"]["elevenlabs"] = {
                    "status": "error",
                    "error": str(elevenlabs_error),
                    "error_type": type(elevenlabs_error).__name__,
                    "duration_seconds": round(duration, 2),
                }
                logger.error(f"❌ ElevenLabs test failed: {str(elevenlabs_error)}")
                
            # Clean up the temporary file
            try:
                os.unlink(temp_file.name)
            except:
                pass
                
    except Exception as e:
        test_results["services"]["elevenlabs"] = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.error(f"❌ ElevenLabs test setup failed: {str(e)}")
    
    # Set overall status
    if (test_results["services"]["google_tts"].get("status") == "healthy" or 
        test_results["services"]["elevenlabs"].get("status") == "healthy"):
        test_results["status"] = "healthy"
    else:
        test_results["status"] = "unhealthy"
    
    return jsonify(test_results)


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
