#!/usr/bin/env python3
"""
Direct check for Veo model access using Google Cloud API
"""

import json
import os
import subprocess
import sys

def run_command(cmd):
    """Run a shell command and return stdout, stderr"""
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr

def get_project_id():
    """Get the current GCP project ID"""
    code, stdout, stderr = run_command("gcloud config get-value project")
    if code == 0 and stdout.strip():
        return stdout.strip()
    return None

def check_model_access(project_id, model_id):
    """Check if a model is accessible using direct API call"""
    print(f"\nChecking access to model: {model_id}")
    
    # First, try to get an auth token
    code, token, stderr = run_command("gcloud auth print-access-token")
    if code != 0 or not token:
        print(f"Error getting auth token: {stderr}")
        return False
    
    token = token.strip()
    
    # Try to access the model directly via API
    model_api_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project_id}/locations/us-central1/publishers/google/models/{model_id}"
    curl_cmd = f"curl -s -H \"Authorization: Bearer {token}\" {model_api_url}"
    
    code, response, stderr = run_command(curl_cmd)
    
    if code != 0:
        print(f"Error making API request: {stderr}")
        return False
    
    try:
        result = json.loads(response)
        if "error" in result:
            print(f"API error: {result['error']['message']}")
            return False
        else:
            print(f"✅ Model accessible!")
            print(f"Model details: {result.get('displayName', 'No display name')} ({result.get('name', 'No name')})")
            return True
    except json.JSONDecodeError:
        print(f"Invalid JSON response: {response}")
        return False

def check_billing_status(project_id):
    """Check if billing is enabled for the project"""
    print("\nChecking billing status...")
    
    cmd = f"gcloud billing projects describe {project_id} --format=json"
    code, stdout, stderr = run_command(cmd)
    
    if code != 0:
        print(f"Error checking billing status: {stderr}")
        return False
    
    try:
        billing_info = json.loads(stdout)
        if "billingEnabled" in billing_info and billing_info["billingEnabled"]:
            billing_account = billing_info.get("billingAccountName", "Unknown").split("/")[-1]
            print(f"✅ Billing is enabled for this project")
            print(f"   Billing account: {billing_account}")
            return True
        else:
            print("❌ Billing is NOT enabled for this project")
            return False
    except json.JSONDecodeError:
        print(f"Failed to parse billing info: {stdout}")
        return False

def main():
    project_id = get_project_id()
    if not project_id:
        print("Error: Could not determine project ID")
        return
    
    print(f"Checking model access for project: {project_id}")
    
    # Check billing status first
    billing_enabled = check_billing_status(project_id)
    
    # Check Veo models
    models = ["veo-2.0-generate-001", "veo-3.0-generate-preview"]
    
    # Also check a model that should be generally accessible as control
    models.append("gemini-1.0-pro")
    
    results = {}
    for model_id in models:
        results[model_id] = check_model_access(project_id, model_id)
    
    # Print summary
    print("\n=== Model Access Summary ===")
    print(f"Billing enabled: {'✅ YES' if billing_enabled else '❌ NO'}")
    for model_id, accessible in results.items():
        status = "✅ ACCESSIBLE" if accessible else "❌ NOT ACCESSIBLE"
        print(f"{status}: {model_id}")
    
    # Print diagnostics if Veo models are not accessible
    if not any(results[model] for model in ["veo-2.0-generate-001", "veo-3.0-generate-preview"]):
        print("\n⚠️ Your project does not have access to Veo models.")
        
        if not billing_enabled:
            print("\n🔍 PRIMARY ISSUE: Billing is not enabled for this project.")
            print("You must enable billing to use Google Cloud AI models:")
            print("1. Go to Google Cloud Console > Billing")
            print("2. Link this project to a billing account with a valid payment method")
        elif not results["gemini-1.0-pro"]:
            print("\n🔍 PRIMARY ISSUE: Your project cannot access ANY AI models.")
            print("This suggests broader configuration issues:")
            print("1. Verify your billing account is in good standing (not suspended)")
            print("2. Check for organization policies restricting AI access")
            print("3. Ensure your account has necessary permissions")
        else:
            print("\n🔍 PRIMARY ISSUE: Your project is not on the allow-list for Veo models.")
            print("To get access:")
            print("1. Go to Google Cloud Console > Vertex AI > Model Garden")
            print("2. Find the Veo model and click 'Apply for access'")
            print("3. Wait for approval (usually within 24 hours)")

if __name__ == "__main__":
    main() 