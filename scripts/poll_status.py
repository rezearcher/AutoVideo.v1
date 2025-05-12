#!/usr/bin/env python3

import requests
import time
import json
from datetime import datetime
import sys

SERVICE_URL = "https://av-app-939407899550.us-central1.run.app"
STATUS_ENDPOINT = f"{SERVICE_URL}/status"
HEALTH_ENDPOINT = f"{SERVICE_URL}/health"
POLL_INTERVAL = 5  # seconds

def check_health(url):
    """Check the health endpoint."""
    try:
        response = requests.get(f"{url}/health")
        return response.status_code == 200
    except Exception as e:
        print(f"Error checking health: {str(e)}")
        return False

def check_status(url):
    """Check the status endpoint."""
    try:
        response = requests.get(f"{url}/status")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: Status endpoint returned {response.status_code}")
            return None
    except Exception as e:
        print(f"Error checking status: {str(e)}")
        return None

def format_timestamp(timestamp):
    """Format timestamp for display."""
    if not timestamp:
        return "N/A"
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp

def format_duration(duration):
    """Format duration for display."""
    if not duration:
        return "N/A"
    try:
        return f"{float(duration):.2f}s"
    except:
        return str(duration)

def print_status(status_data):
    """Print the status information."""
    if not status_data:
        return
        
    print("\n==================================================")
    print(f"Status Check at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    print(f"Generation Status: {'Generating' if status_data.get('is_generating') else 'Idle'}")
    print(f"System Initialized: {'Yes' if status_data.get('is_initialized') else 'No'}")
    print(f"Last Generation: {format_timestamp(status_data.get('last_generation_time'))}")
    print(f"Last Status: {status_data.get('last_generation_status', 'N/A')}")
    
    print("\nTiming Metrics:")
    timing_metrics = status_data.get('timing_metrics', {})
    if timing_metrics:
        for phase, duration in timing_metrics.items():
            print(f"  {phase}: {format_duration(duration)}")
    else:
        print("  No timing metrics available")

def main():
    """Main polling function."""
    print("Starting status polling...")
    print(f"Service URL: {SERVICE_URL}")
    print(f"Polling interval: {POLL_INTERVAL} seconds")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # First check health
            if check_health(SERVICE_URL):
                # If healthy, check status
                status_data = check_status(SERVICE_URL)
                if status_data:
                    print_status(status_data)
            else:
                print(f"\nService health check failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        print("\nPolling stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError during polling: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 