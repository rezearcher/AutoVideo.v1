"""Service for checking and managing API quota limits."""

import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class QuotaGuardService:
    """Service for checking and managing API quota limits."""

    # Cache the quota check results to avoid repeated API calls
    _cache = {}
    _cache_expires = {}
    # Default cache TTL in seconds
    _cache_ttl = 300  # 5 minutes

    @classmethod
    def check_veo_quota(
        cls, min_available_tokens: int = 40
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if there is sufficient Veo API quota available.

        Args:
            min_available_tokens: Minimum number of tokens that should be available

        Returns:
            Tuple of (is_sufficient, details)
        """
        # Check cache first
        cache_key = "veo"
        if cache_key in cls._cache and time.time() < cls._cache_expires.get(
            cache_key, 0
        ):
            logger.debug("Using cached Veo quota information")
            quota_info = cls._cache[cache_key]
            return cls._evaluate_veo_quota(quota_info, min_available_tokens)

        project_id = settings.GCP_PROJECT
        if not project_id:
            logger.error("No GCP project ID set, cannot check quota")
            return False, {"error": "No GCP project ID set"}

        try:
            # This is the correct format for the gcloud services quota command
            command = [
                "gcloud",
                "services",
                "quota",
                "check",
                f"--project={project_id}",
                "--service=generativelanguage.googleapis.com",
                "--json",
            ]

            logger.debug(f"Running quota check command: {' '.join(command)}")
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )

            if result.returncode != 0:
                logger.error(f"Error checking Veo quota: {result.stderr}")
                return False, {"error": f"Command failed: {result.stderr}"}

            # Parse the JSON output
            try:
                quota_info = json.loads(result.stdout)

                # Cache the results
                cls._cache[cache_key] = quota_info
                cls._cache_expires[cache_key] = time.time() + cls._cache_ttl

                return cls._evaluate_veo_quota(quota_info, min_available_tokens)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse quota check output: {e}")
                return False, {"error": f"Failed to parse output: {e}"}

        except Exception as e:
            logger.error(f"Error checking Veo quota: {e}")
            return False, {"error": str(e)}

    @staticmethod
    def _evaluate_veo_quota(
        quota_info: Dict[str, Any], min_available_tokens: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate the Veo quota information to determine if there's sufficient quota.

        Args:
            quota_info: Quota information from gcloud command
            min_available_tokens: Minimum tokens required

        Returns:
            Tuple of (is_sufficient, details)
        """
        try:
            # Extract the relevant metrics
            metrics = {}
            available_tokens = None

            if "consumerQuotaLimits" in quota_info:
                for limit in quota_info["consumerQuotaLimits"]:
                    if (
                        "metric" in limit
                        and "VertexGenerativeAi-GenerateContent" in limit["metric"]
                    ):
                        metrics["metric"] = limit["metric"]

                        if "quotaLimit" in limit:
                            metrics["limit"] = limit["quotaLimit"]

                        if "metricRules" in limit and limit["metricRules"]:
                            # Get current usage
                            current_usage = limit["metricRules"][0].get(
                                "currentUsage", 0
                            )
                            metrics["usage"] = current_usage

                            # Calculate available tokens
                            if "limit" in metrics:
                                available_tokens = metrics["limit"] - current_usage
                                metrics["available"] = available_tokens

            if available_tokens is None:
                logger.warning("Could not determine available Veo tokens")
                return False, {
                    "error": "Could not determine available tokens",
                    "quota_info": quota_info,
                }

            # Check if we have sufficient tokens
            is_sufficient = available_tokens >= min_available_tokens

            if not is_sufficient:
                logger.warning(
                    f"Insufficient Veo tokens: {available_tokens} available, "
                    f"{min_available_tokens} required"
                )
            else:
                logger.info(
                    f"Sufficient Veo tokens available: {available_tokens} "
                    f"(minimum required: {min_available_tokens})"
                )

            return is_sufficient, {
                "sufficient": is_sufficient,
                "available_tokens": available_tokens,
                "required_tokens": min_available_tokens,
                "metrics": metrics,
            }

        except Exception as e:
            logger.error(f"Error evaluating Veo quota: {e}")
            return False, {"error": str(e), "quota_info": quota_info}

    @classmethod
    def wait_for_sufficient_quota(
        cls,
        service: str,
        min_available: int,
        max_retries: int = 5,
        retry_delay: int = 60,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Wait for sufficient quota to be available, with exponential backoff.

        Args:
            service: Service name ("veo")
            min_available: Minimum available quota required
            max_retries: Maximum number of retries
            retry_delay: Initial retry delay in seconds

        Returns:
            Tuple of (success, details)
        """
        retry_count = 0
        current_delay = retry_delay

        while retry_count <= max_retries:
            logger.info(
                f"Checking {service} quota (attempt {retry_count + 1}/{max_retries + 1})"
            )

            if service.lower() == "veo":
                sufficient, details = cls.check_veo_quota(min_available)
            else:
                return False, {"error": f"Unknown service: {service}"}

            if sufficient:
                return True, details

            retry_count += 1
            if retry_count > max_retries:
                logger.warning(
                    f"Exceeded maximum retries ({max_retries}) waiting for {service} quota"
                )
                return False, details

            logger.info(f"Waiting {current_delay}s before retrying...")
            time.sleep(current_delay)
            current_delay *= 2  # Exponential backoff

        return False, {"error": "Failed to acquire sufficient quota"}


if __name__ == "__main__":
    # For testing/debug
    logging.basicConfig(level=logging.DEBUG)
    sufficient, details = QuotaGuardService.check_veo_quota()
    print(f"Sufficient quota: {sufficient}")
    print(f"Details: {json.dumps(details, indent=2)}")
