#!/usr/bin/env python3
"""
Veo API Hidden Gate Checker - Detects which specific gate is blocking your Veo API access
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("veo-gate-check")

def run_command(cmd: str) -> Tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, and stderr"""
    logger.debug(f"Running command: {cmd}")
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr

def get_project_id() -> Optional[str]:
    """Get the current GCP project ID"""
    exit_code, stdout, stderr = run_command("gcloud config get-value project")
    if exit_code == 0 and stdout.strip():
        return stdout.strip()
    logger.error(f"Failed to get project ID: {stderr}")
    return None

def check_model_visibility(project_id: str, model_name: str = "veo-3.0-generate-preview") -> bool:
    """Check if the model is visible to the project"""
    logger.info(f"Checking if model {model_name} is visible to project {project_id}...")
    
    cmd = f"gcloud ai models describe projects/{project_id}/locations/us-central1/publishers/google/models/{model_name} --format='value(name)'"
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code == 0 and stdout.strip():
        logger.info(f"✅ Model {model_name} is visible to your project")
        return True
    else:
        logger.error(f"❌ Model {model_name} is NOT visible to your project")
        logger.error(f"Error: {stderr.strip()}")
        logger.error("Your project may not be on the allow-list for this model")
        return False

def check_veo_2_model_visibility(project_id: str) -> bool:
    """Check if Veo 2.0 model is visible"""
    return check_model_visibility(project_id, "veo-2.0-generate-001")

def check_service_account_role(project_id: str) -> bool:
    """Check if the service account has the aiplatform.user role"""
    logger.info(f"Checking if service account has aiplatform.user role...")
    
    # Get the service account name
    cmd = f"gcloud projects describe {project_id} --format='value(projectNumber)'"
    exit_code, project_number, stderr = run_command(cmd)
    
    if exit_code != 0 or not project_number.strip():
        logger.error(f"Failed to get project number: {stderr}")
        return False
    
    service_account = f"service-{project_number.strip()}@gcp-sa-aiplatform.iam.gserviceaccount.com"
    logger.info(f"Service account: {service_account}")
    
    # Check if the service account has the aiplatform.user role
    cmd = f"gcloud projects get-iam-policy {project_id} --filter=\"bindings.members:'{service_account}'\" --format=json"
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code != 0:
        logger.error(f"Failed to get IAM policy: {stderr}")
        return False
    
    try:
        policy = json.loads(stdout)
        for binding in policy.get("bindings", []):
            if binding.get("role") == "roles/aiplatform.user" and service_account in binding.get("members", []):
                logger.info(f"✅ Service account has aiplatform.user role")
                return True
    except json.JSONDecodeError:
        logger.error(f"Failed to parse IAM policy: {stdout}")
        return False
    
    logger.error(f"❌ Service account does NOT have aiplatform.user role")
    return False

def check_region_initialization() -> bool:
    """Check if code is using the correct region"""
    logger.info("Checking region initialization in code...")
    
    # Search for vertexai.init or region in python files
    cmd = "grep -r \"vertexai.init\" --include=\"*.py\" ."
    exit_code, stdout, stderr = run_command(cmd)
    
    if "us-central1" in stdout:
        logger.info("✅ Found code initializing with correct region (us-central1)")
        return True
    elif "vertexai.init" in stdout:
        logger.warning("⚠️ Found vertexai.init but without explicit us-central1 region")
        logger.warning("Code snippets found:")
        for line in stdout.strip().split("\n"):
            logger.warning(f"  {line}")
        return False
    else:
        logger.warning("⚠️ Could not find vertexai.init in code")
        return False

def try_zero_token_request(model_name: str = "veo-2.0-generate-001") -> bool:
    """Try a zero-token request to check if we can connect to the API"""
    logger.info(f"Attempting a zero-token API request to {model_name}...")
    
    try:
        # Try to import the package
        import_cmd = "python -c \"try: from vertexai.preview.generative_models import GenerativeModel; print('Import successful'); exit(0)\\nexcept Exception as e: print(f'Import failed: {e}'); exit(1)\""
        exit_code, stdout, stderr = run_command(import_cmd)
        
        if exit_code != 0:
            logger.error(f"❌ Failed to import required packages: {stdout}")
            return False
        
        # Create a temporary test script
        test_script = "temp_veo_test.py"
        with open(test_script, "w") as f:
            f.write(f"""
import os
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

# Force region to us-central1
import vertexai
vertexai.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location="us-central1")

# Use minimal tokens
model = GenerativeModel("{model_name}")
config = GenerationConfig(temperature=0.1, max_output_tokens=1, top_p=0.1, top_k=1)
try:
    response = model.generate_content("test", generation_config=config)
    print("✅ API request succeeded!")
    exit(0)
except Exception as e:
    print(f"❌ API request failed: {{e}}")
    exit(1)
""")
        
        # Run the test script
        cmd = f"python {test_script}"
        exit_code, stdout, stderr = run_command(cmd)
        
        # Clean up
        os.remove(test_script)
        
        if exit_code == 0 and "succeeded" in stdout:
            logger.info("✅ Zero-token request succeeded!")
            return True
        else:
            logger.error(f"❌ Zero-token request failed:")
            logger.error(stdout)
            return False
    
    except Exception as e:
        logger.error(f"❌ Error during zero-token test: {e}")
        return False

def grant_service_account_role(project_id: str) -> bool:
    """Grant the aiplatform.user role to the service account"""
    logger.info(f"Granting aiplatform.user role to service account...")
    
    # Get the service account name
    cmd = f"gcloud projects describe {project_id} --format='value(projectNumber)'"
    exit_code, project_number, stderr = run_command(cmd)
    
    if exit_code != 0 or not project_number.strip():
        logger.error(f"Failed to get project number: {stderr}")
        return False
    
    service_account = f"service-{project_number.strip()}@gcp-sa-aiplatform.iam.gserviceaccount.com"
    
    # Grant the role
    cmd = f"gcloud projects add-iam-policy-binding {project_id} --member=\"serviceAccount:{service_account}\" --role=\"roles/aiplatform.user\""
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code == 0:
        logger.info(f"✅ Successfully granted aiplatform.user role to service account")
        return True
    else:
        logger.error(f"❌ Failed to grant role: {stderr}")
        return False

def run_checks() -> Dict[str, bool]:
    """Run all checks and return results"""
    results = {}
    
    # Get project ID
    project_id = get_project_id()
    if not project_id:
        logger.error("Cannot proceed without a valid project ID")
        return {"project_id": False}
    
    results["project_id"] = True
    logger.info(f"Using project: {project_id}")
    
    # Check model visibility for Veo 3.0
    results["veo3_visible"] = check_model_visibility(project_id)
    
    # Check model visibility for Veo 2.0
    results["veo2_visible"] = check_veo_2_model_visibility(project_id)
    
    # Check service account role
    results["service_account_role"] = check_service_account_role(project_id)
    
    # Check region initialization
    results["correct_region"] = check_region_initialization()
    
    # Try a zero-token request
    model_to_test = "veo-2.0-generate-001" if results["veo2_visible"] else "veo-3.0-generate-preview"
    results["api_connection"] = try_zero_token_request(model_to_test)
    
    return results

def apply_fixes(results: Dict[str, bool], args: argparse.Namespace) -> None:
    """Apply fixes based on check results"""
    project_id = get_project_id()
    if not project_id:
        logger.error("Cannot apply fixes without a valid project ID")
        return
    
    # Check if service account role needs to be granted
    if not results.get("service_account_role", False) and args.fix_service_account:
        logger.info("Attempting to fix service account role...")
        grant_service_account_role(project_id)
    
    # Print instructions for other issues
    if not results.get("veo3_visible", False) and not results.get("veo2_visible", False):
        logger.info("\n=== Model Visibility Fix ===")
        logger.info("Your project is not on the allow-list for Veo models.")
        logger.info("To fix this:")
        logger.info("1. Go to Google Cloud Console > Vertex AI > Model Garden")
        logger.info("2. Find the Veo model you want to use")
        logger.info("3. Click 'Apply for access' and fill out the form")
        logger.info("4. Wait for approval (usually within 24 hours)")
    
    if not results.get("correct_region", False):
        logger.info("\n=== Region Fix ===")
        logger.info("Your code may not be using the correct region (us-central1).")
        logger.info("To fix this, add the following to your code before using Veo:")
        logger.info("```python")
        logger.info("import vertexai")
        logger.info("vertexai.init(project=PROJECT_ID, location=\"us-central1\")")
        logger.info("```")

def main():
    parser = argparse.ArgumentParser(description="Check for hidden gates blocking Veo API access")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues automatically")
    parser.add_argument("--fix-service-account", action="store_true", help="Grant aiplatform.user role to service account")
    args = parser.parse_args()
    
    logger.info("=== Veo API Hidden Gate Checker ===")
    
    # Run checks
    results = run_checks()
    
    # Print summary
    logger.info("\n=== Check Results ===")
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {check}")
    
    # Apply fixes if requested
    if args.fix or args.fix_service_account:
        apply_fixes(results, args)
    
    # Final diagnosis
    if all(results.values()):
        logger.info("\n🎉 All checks passed! Your Veo API access should be working correctly.")
    else:
        logger.info("\n⚠️ Some checks failed. Review the output above for details and suggested fixes.")
        if not args.fix and not args.fix_service_account:
            logger.info("Run this script with --fix to attempt automatic fixes.")

if __name__ == "__main__":
    main() 