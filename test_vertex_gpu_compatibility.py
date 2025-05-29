#!/usr/bin/env python3
"""
Test script to validate GPU machine type compatibility across regions
"""

import logging
import os

from vertex_gpu_service import (
    REGION_GPU_MACHINE_MAP,
    discover_gpu_machine_compatibility,
    get_machine_type_for_gpu,
    get_multi_region_quota_status,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_static_mappings():
    """Test the static machine type mappings"""
    logger.info("🧪 Testing static machine type mappings...")

    for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
        logger.info(f"\n📍 Region: {region}")
        for gpu_type, machine_type in gpu_map.items():
            logger.info(f"  {gpu_type} -> {machine_type}")

    logger.info("✅ Static mappings test completed")


def test_dynamic_discovery():
    """Test dynamic GPU machine type discovery"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning(
            "⚠️ GOOGLE_CLOUD_PROJECT not set, skipping dynamic discovery test"
        )
        return

    logger.info("🔍 Testing dynamic GPU machine type discovery...")

    test_regions = ["us-central1", "europe-west1", "us-west1"]

    for region in test_regions:
        logger.info(f"\n📍 Testing region: {region}")
        try:
            compatibility = discover_gpu_machine_compatibility(project_id, region)
            logger.info(f"  Discovered compatibility: {compatibility}")
        except Exception as e:
            logger.error(f"  ❌ Discovery failed: {e}")

    logger.info("✅ Dynamic discovery test completed")


def test_machine_type_lookup():
    """Test the machine type lookup function"""
    logger.info("🔧 Testing machine type lookup function...")

    test_cases = [
        ("us-central1", "NVIDIA_L4"),
        ("us-central1", "NVIDIA_TESLA_T4"),
        ("us-west1", "NVIDIA_L4"),  # Should return None (not available)
        ("us-west1", "NVIDIA_TESLA_T4"),
        ("europe-west1", "NVIDIA_L4"),
        ("nonexistent-region", "NVIDIA_L4"),  # Should return None
    ]

    for region, gpu_type in test_cases:
        machine_type = get_machine_type_for_gpu(region, gpu_type)
        status = "✅" if machine_type else "❌"
        logger.info(f"  {status} {region} + {gpu_type} -> {machine_type}")

    logger.info("✅ Machine type lookup test completed")


def test_quota_status():
    """Test multi-region quota status check"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("⚠️ GOOGLE_CLOUD_PROJECT not set, skipping quota status test")
        return

    logger.info("📊 Testing multi-region quota status...")

    try:
        quota_status = get_multi_region_quota_status(project_id)

        for region, region_status in quota_status.items():
            logger.info(f"\n📍 Region: {region}")
            for gpu_type, status in region_status.items():
                available = status.get("available", 0)
                quota_ok = status.get("quota_ok", False)
                status_icon = "✅" if quota_ok else "❌"
                logger.info(f"  {status_icon} {gpu_type}: {available} available")

    except Exception as e:
        logger.error(f"❌ Quota status test failed: {e}")

    logger.info("✅ Quota status test completed")


def main():
    """Run all tests"""
    logger.info("🚀 Starting GPU compatibility tests...")

    test_static_mappings()
    test_machine_type_lookup()
    test_dynamic_discovery()
    test_quota_status()

    logger.info("🎉 All tests completed!")


if __name__ == "__main__":
    main()
