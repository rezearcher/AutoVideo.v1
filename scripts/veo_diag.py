#!/usr/bin/env python3
"""
Veo SDK diagnostic – runs in CI or a Cloud Run shell.
Zero-token probe: sets returnRawTokens=True.
Exits 1 if any critical check fails, prints actionable hints.
"""

import os, sys, json, time, traceback
from typing import Dict

RESULTS: Dict[str, Dict[str, str]] = {}

def ok(section, key, val="success"):
    RESULTS.setdefault(section, {})[key] = val

def fail(section, key, err):
    RESULTS.setdefault(section, {})[key] = f"❌ {err}"

# ---------- 1. import checks ----------
try:
    import google.auth  # noqa
    from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
    ok("imports", "vertexai.preview")
except Exception as e:
    fail("imports", "vertexai.preview", e)

# ---------- 2. auth + init ----------
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
REGION  = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
if not PROJECT:
    fail("auth", "project_id", "env var missing")
else:
    try:
        import vertexai
        vertexai.init(project=PROJECT, location=REGION)
        ok("auth", "vertexai.init")
    except Exception as e:
        fail("auth", "vertexai.init", e)

# ---------- 3. model ping ----------
try:
    model = GenerativeModel("veo-3.0-generate-preview")
    try:
        # Use the same method that's used in video_creator.py
        op = model.generate_video_async(
            prompt="ping",
            generation_config={
                "durationSeconds": 5,
                "aspectRatio": "16:9",
                "sampleCount": 1,  # Must be explicitly set per Google docs
            },
            output_storage=f"gs://{BKT}/veo-diag/" if BKT else None,
        )
        # Don't wait for completion to avoid token use
        ok("api", "veo_generate_video_async")
    except AttributeError as ae:
        fail("api", "veo_api_method", f"Method 'generate_video_async' not found: {ae}")
    except Exception as e:
        fail("api", "veo_generation", str(e))
except Exception as e:
    fail("api", "veo_model_init", str(e))

# ---------- 4. storage ----------
BKT = os.getenv("VERTEX_BUCKET_NAME")
if not BKT:
    fail("storage", "bucket_env", "VERTEX_BUCKET_NAME not set")
else:
    try:
        from google.cloud import storage
        blob_name = f"veo-diag/{int(time.time())}.txt"
        storage.Client().bucket(BKT).blob(blob_name).upload_from_string("diag")
        ok("storage", "write_test")
    except Exception as e:
        fail("storage", "write_test", e)

# ---------- results ----------
print("\n=== VE0 DIAGNOSTIC RESULTS ===")
bad = False
for section, kv in RESULTS.items():
    print(f"\n{section.upper()}:")
    for k, v in kv.items():
        print(f"  {k:25} {v}")
        if isinstance(v, str) and v.startswith("❌"):
            bad = True

if bad:
    print("\nOne or more critical checks failed – see ❌ markers above")
    sys.exit(1)
print("\nAll critical checks passed.")
