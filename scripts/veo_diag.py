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
    op = model.generate_video_async(
        "ping", generation_config=GenerationConfig(
            duration_seconds=5, aspect_ratio="16:9",
            sample_count=1, return_raw_tokens=True
        )
    )
    op.result(timeout=120)
    ok("api", "veo_generate_async")
except Exception as e:
    fail("api", "veo_generate_async", e)

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
