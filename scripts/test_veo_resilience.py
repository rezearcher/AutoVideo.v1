#!/usr/bin/env python3
"""
Test the Veo resilience improvements by simulating multiple simultaneous video generation requests
and verifying that token quota limits are respected and the prompt cache is working.
"""

import argparse
import concurrent.futures
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional

# Add the project root to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.config import settings
    from app.services.prompt_cache import PromptCacheService
    from app.services.storage_service import StorageService
    from app.services.veo_service import VeoService
except ImportError:
    print("⚠️ Failed to import app modules. Run this script from the project root.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("veo_resilience_test")

# List of simple test prompts
TEST_PROMPTS = [
    "a golden retriever running through a meadow with wildflowers",
    "aerial view of a tropical beach with turquoise water",
    "a red sports car driving on a mountain road, drone view",
    "a space shuttle launch from ground view with dramatic clouds",
    "a time-lapse of a flower blooming in sunlight",
    "sunset over the mountains with golden light",
    "a waterfall in a lush green forest",
    "a cityscape at night with glowing lights",
    "a hot air balloon floating over a colorful landscape",
    "snow falling in a quiet forest",
]


def generate_video(
    veo_service: VeoService, prompt: str, duration: int = 5, use_cache: bool = True
) -> Optional[str]:
    """
    Generate a video using the Veo service.

    Args:
        veo_service: The VeoService instance
        prompt: The video prompt
        duration: Duration in seconds
        use_cache: Whether to use the prompt cache

    Returns:
        URL of the generated video or None if generation failed
    """
    logger.info(
        f"Generating video for prompt: '{prompt[:30]}...' (use_cache={use_cache})"
    )

    start_time = time.time()
    url = veo_service.generate_video(
        prompt=prompt,
        duration_seconds=duration,
        aspect_ratio="16:9",
        reference_image_path=None,
        check_quota=True,
        use_cache=use_cache,
    )

    duration = time.time() - start_time

    if url:
        logger.info(f"✅ Video generated in {duration:.1f} seconds: {url}")
    else:
        logger.error(f"❌ Failed to generate video after {duration:.1f} seconds")

    return url


def run_parallel_test(
    veo_service: VeoService,
    prompts: List[str],
    max_workers: int = 3,
    use_cache: bool = True,
) -> List[str]:
    """
    Run a parallel test with multiple video generation requests.

    Args:
        veo_service: The VeoService instance
        prompts: List of prompts to use
        max_workers: Maximum number of concurrent workers
        use_cache: Whether to use the prompt cache

    Returns:
        List of generated video URLs
    """
    logger.info(
        f"Starting parallel test with {len(prompts)} prompts and {max_workers} workers"
    )

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_prompt = {
            executor.submit(generate_video, veo_service, prompt, 5, use_cache): prompt
            for prompt in prompts
        }

        for future in concurrent.futures.as_completed(future_to_prompt):
            prompt = future_to_prompt[future]
            try:
                url = future.result()
                if url:
                    results.append(url)
            except Exception as e:
                logger.error(
                    f"Error generating video for prompt '{prompt[:30]}...': {e}"
                )

    return results


def run_cache_test(veo_service: VeoService, prompts: List[str]) -> None:
    """
    Test the prompt cache by generating the same videos twice.

    Args:
        veo_service: The VeoService instance
        prompts: List of prompts to use
    """
    logger.info("\n========== CACHE TEST ==========")
    logger.info("Running first pass (no cache hits expected)...")

    # First pass - should generate new videos
    first_pass_start = time.time()
    first_pass_results = []

    for prompt in prompts:
        url = generate_video(veo_service, prompt, use_cache=True)
        if url:
            first_pass_results.append(url)

    first_pass_duration = time.time() - first_pass_start

    logger.info(f"First pass completed in {first_pass_duration:.1f} seconds")
    logger.info(f"Generated {len(first_pass_results)} videos")

    # Short delay to ensure cache is written
    time.sleep(2)

    logger.info("\nRunning second pass (cache hits expected)...")

    # Second pass - should use cached videos
    second_pass_start = time.time()
    second_pass_results = []

    for prompt in prompts:
        url = generate_video(veo_service, prompt, use_cache=True)
        if url:
            second_pass_results.append(url)

    second_pass_duration = time.time() - second_pass_start

    logger.info(f"Second pass completed in {second_pass_duration:.1f} seconds")
    logger.info(f"Retrieved {len(second_pass_results)} videos")

    # Calculate savings
    if first_pass_duration > 0:
        savings_pct = (
            (first_pass_duration - second_pass_duration) / first_pass_duration
        ) * 100
        logger.info(f"Cache provided {savings_pct:.1f}% time savings")

    # Verify cache is working by checking for mismatches
    if len(first_pass_results) != len(second_pass_results):
        logger.warning("Cache test: URL count mismatch between passes")

    matched = sum(
        1 for u1, u2 in zip(first_pass_results, second_pass_results) if u1 == u2
    )
    logger.info(
        f"Cache test: {matched}/{len(first_pass_results)} URLs matched between passes"
    )


def run_quota_test(veo_service: VeoService, num_requests: int = 10) -> None:
    """
    Test quota handling by sending more requests than the quota allows.

    Args:
        veo_service: The VeoService instance
        num_requests: Number of requests to make
    """
    logger.info("\n========== QUOTA TEST ==========")
    logger.info(f"Attempting to generate {num_requests} videos simultaneously")
    logger.info(
        "This will likely exceed the per-minute quota and test backoff behavior"
    )

    # Select random prompts from the test set
    test_prompts = random.choices(TEST_PROMPTS, k=num_requests)

    # Run parallel test with cache disabled
    start_time = time.time()
    results = run_parallel_test(
        veo_service, test_prompts, max_workers=num_requests, use_cache=False
    )
    duration = time.time() - start_time

    success_rate = (len(results) / num_requests) * 100

    logger.info(f"Quota test completed in {duration:.1f} seconds")
    logger.info(
        f"Successfully generated {len(results)}/{num_requests} videos ({success_rate:.1f}%)"
    )


def main():
    parser = argparse.ArgumentParser(description="Test Veo resilience improvements")
    parser.add_argument(
        "--test", choices=["cache", "quota", "all"], default="all", help="Test to run"
    )
    parser.add_argument(
        "--quota-requests",
        type=int,
        default=10,
        help="Number of requests for quota test",
    )
    parser.add_argument(
        "--cache-prompts", type=int, default=3, help="Number of prompts for cache test"
    )
    args = parser.parse_args()

    # Initialize services
    storage_service = StorageService()
    veo_service = VeoService(storage_service)

    # Check if Veo is available
    if not veo_service.is_available():
        logger.error(
            "❌ Veo service is not available. Please check your configuration."
        )
        sys.exit(1)

    # Check if prompt cache is enabled
    health = veo_service.health_check()
    if not health.get("cache_enabled", False):
        logger.warning(
            "⚠️ Prompt cache is disabled. Enable PROMPT_CACHE_ENABLED for full test."
        )

    logger.info(f"Veo health check: {health}")

    # Run selected tests
    if args.test in ["cache", "all"]:
        # Select a subset of prompts for cache test
        cache_prompts = random.sample(
            TEST_PROMPTS, min(args.cache_prompts, len(TEST_PROMPTS))
        )
        run_cache_test(veo_service, cache_prompts)

    if args.test in ["quota", "all"]:
        run_quota_test(veo_service, args.quota_requests)

    logger.info("\n✅ All tests completed!")


if __name__ == "__main__":
    main()
