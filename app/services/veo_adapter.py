import logging
import os
import time
import uuid

from google.cloud import storage
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

_MODEL_ID = os.getenv("VEO_MODEL", "veo-3.0-generate-preview")
_BUCKET = os.getenv("VERTEX_BUCKET_NAME")
_TIMEOUT = int(os.getenv("VEO_OP_TIMEOUT", 900))  # 15 min
_LOG = logging.getLogger("veo")


def make_clip(prompt: str, seconds: int = 8) -> str:
    """Returns a **local** MP4 path — raises on any failure."""
    if not 5 <= seconds <= 8:
        raise ValueError("Veo 3 only supports 5-8 s duration")

    model = GenerativeModel(_MODEL_ID)
    op = model.generate_video_async(
        prompt,
        generation_config=GenerationConfig(
            duration_seconds=seconds,
            aspect_ratio="16:9",
            sample_count=1,  # **required**
            return_raw_tokens=True,  # zero-token smoke probe
        ),
        output_storage=f"gs://{_BUCKET}/veo-temp/",
    )

    _LOG.info("Veo LRO %s started", op.operation.name)
    rsp = op.result(timeout=_TIMEOUT)

    # robust to API structure drift
    uri = getattr(rsp, "videos", [{}])[0].get("gcs_uri") or getattr(
        rsp, "generatedSamples", [{}]
    )[0].get("video", {}).get("uri")
    if not uri:
        raise RuntimeError("No gcs uri in Veo response")

    local = f"/tmp/clip_{uuid.uuid4().hex[:8]}.mp4"
    storage.Client().download_blob_to_file(uri, open(local, "wb"))
    return local
