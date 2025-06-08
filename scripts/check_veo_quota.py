#!/usr/bin/env python3
"""
Check Veo API quota and token usage.
This script displays real-time token usage and quota information for Veo API.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# Add the project root to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.config import settings
    from app.services.quota_guard import QuotaGuardService
except ImportError:
    print("⚠️ Failed to import app modules. Run this script from the project root.")
    sys.exit(1)


def check_monitoring_available():
    """Check if gcloud monitoring is available in this environment."""
    try:
        # Check if gcloud monitoring is available
        check_cmd = ["gcloud", "help", "monitoring"]
        check_result = subprocess.run(
            check_cmd, capture_output=True, text=True, check=False
        )

        if (
            check_result.returncode != 0
            or "ERROR: (gcloud.monitoring)" in check_result.stderr
        ):
            print("⚠️ gcloud monitoring not available in this environment")
            return False

        # Check if time-series command is available
        cmd = ["gcloud", "monitoring", "time-series", "--help"]
        help_result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if (
            help_result.returncode != 0
            or "Invalid choice: 'time-series'" in help_result.stderr
        ):
            print("⚠️ gcloud monitoring time-series not available in this environment")
            return False

        return True
    except Exception as e:
        print(f"⚠️ Error checking monitoring availability: {e}")
        return False


def get_tokens_in_use():
    """
    Get the current number of tokens in use for Veo API.
    Uses the monitoring API for real-time usage data.

    Returns:
        Current token usage (0 if unable to determine)
    """
    try:
        if not check_monitoring_available():
            print("ℹ️ Monitoring not available, cannot check real-time token usage")
            return 0

        project_id = os.environ.get("GCP_PROJECT", settings.GCP_PROJECT)
        if not project_id:
            print("❌ No GCP project ID set. Set GCP_PROJECT environment variable.")
            return 0

        cmd = [
            "gcloud",
            "monitoring",
            "time-series",
            "list",
            f"--project={project_id}",
            '--filter=metric.type="aiplatform.googleapis.com/generative/tokens_in_use" AND metric.label."base_model"="veo-3.0-generate-001"',
            "--limit=1",
            "--format=value(point.value.int64Value)",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            print(f"⚠️ Could not check token usage: {result.stderr}")
            return 0

        # Parse the token usage
        tokens_in_use = 0
        if result.stdout.strip():
            tokens_in_use = int(result.stdout.strip())

        return tokens_in_use

    except Exception as e:
        print(f"⚠️ Error checking token usage: {e}")
        return 0


def watch_token_usage(interval=5, max_minutes=5):
    """
    Watch token usage in real-time.

    Args:
        interval: Refresh interval in seconds
        max_minutes: Maximum minutes to watch
    """
    if not check_monitoring_available():
        print("❌ Cannot watch token usage - gcloud monitoring not available")
        return

    max_tokens_per_minute = int(os.environ.get("VEO_LIMIT_MPM", settings.VEO_LIMIT_MPM))

    print(
        f"\n🔍 Monitoring Veo token usage (refresh: {interval}s, limit: {max_tokens_per_minute}/min)"
    )
    print(f"Press Ctrl+C to stop monitoring\n")

    start_time = time.time()
    end_time = start_time + (max_minutes * 60)

    try:
        while time.time() < end_time:
            tokens_in_use = get_tokens_in_use()
            tokens_available = max_tokens_per_minute - tokens_in_use

            # Calculate percentage used
            percent_used = (
                (tokens_in_use / max_tokens_per_minute) * 100
                if max_tokens_per_minute > 0
                else 0
            )

            # Progress bar
            bar_length = 40
            filled_length = int(bar_length * tokens_in_use / max_tokens_per_minute)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)

            current_time = datetime.now().strftime("%H:%M:%S")

            # Color coding based on usage
            if percent_used < 50:
                status = "✅ GOOD"
            elif percent_used < 80:
                status = "⚠️ MODERATE"
            else:
                status = "❌ HIGH"

            print(
                f"[{current_time}] {bar} {tokens_in_use}/{max_tokens_per_minute} tokens ({percent_used:.1f}%) - {status}",
                end="\r",
            )

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped by user")

    print("\n")


def check_quotas():
    """Check quota limits and usage for Veo API."""
    print("\n🔍 Checking Veo API quota limits and usage...\n")

    has_quota, quota_details = QuotaGuardService.check_veo_quota()

    if not has_quota:
        print("❌ Insufficient quota available")
    else:
        print("✅ Quota available")

    # Display quota details
    print("\nQuota Details:")
    print(f"  Daily Limit: {quota_details.get('daily_limit', 'Unknown')}")
    print(f"  Daily Usage: {quota_details.get('daily_usage', 'Unknown')}")
    print(f"  Minute Limit: {quota_details.get('minute_limit', 'Unknown')}")
    print(f"  Minute Usage: {quota_details.get('minute_usage', 'Unknown')}")

    # Display current token usage
    tokens_in_use = get_tokens_in_use()
    if tokens_in_use > 0:
        max_tokens_per_minute = int(
            os.environ.get("VEO_LIMIT_MPM", settings.VEO_LIMIT_MPM)
        )
        print(
            f"\nCurrent Token Usage: {tokens_in_use}/{max_tokens_per_minute} tokens per minute"
        )

        # Recommendation
        if tokens_in_use > (max_tokens_per_minute * 0.8):
            print(
                "\n⚠️ High token usage detected. Consider waiting before making new requests."
            )
    else:
        print("\nCurrent Token Usage: Not available (monitoring API not accessible)")

    # Request a quota increase if needed
    if quota_details.get("daily_usage", 0) > (
        quota_details.get("daily_limit", 1) * 0.8
    ):
        print("\n💡 Recommendation: Consider requesting a quota increase:")
        print("   Console → IAM & Admin → Quota → filter 'Generative Video Tokens'")
        print("   → Edit Quota → request '500 per minute, 20,000 per day'")


def main():
    parser = argparse.ArgumentParser(description="Check Veo API quota and token usage")
    parser.add_argument(
        "--watch", action="store_true", help="Watch token usage in real-time"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds for watch mode",
    )
    parser.add_argument(
        "--minutes", type=int, default=5, help="Maximum minutes to watch"
    )
    args = parser.parse_args()

    if args.watch:
        watch_token_usage(args.interval, args.minutes)
    else:
        check_quotas()


if __name__ == "__main__":
    main()
