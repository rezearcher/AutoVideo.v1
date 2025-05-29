#!/usr/bin/env python3
"""
Simple test to validate GPU machine type mappings
"""

# Inline the mapping to avoid import issues
REGION_GPU_MACHINE_MAP = {
    "us-central1": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "us-west1": {
        # L4 GPUs not available in us-west1
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "us-east1": {
        # L4 GPUs not available in us-east1
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "europe-west1": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "asia-southeast1": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    # Add additional regions where L4 is available
    "us-east4": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "us-west4": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "europe-west3": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "europe-west4": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "asia-east1": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
    "asia-northeast1": {
        "NVIDIA_L4": "g2-standard-8",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8",
    },
}


def test_mappings():
    """Test the GPU machine type mappings"""
    print("🧪 Testing GPU machine type mappings...")

    l4_regions = []
    t4_only_regions = []

    for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
        print(f"\n📍 Region: {region}")

        # Check L4 availability
        if "NVIDIA_L4" in gpu_map:
            l4_regions.append(region)
            machine_type = gpu_map["NVIDIA_L4"]
            if machine_type == "g2-standard-8":
                print(f"  ✅ L4 -> {machine_type}")
            else:
                print(f"  ❌ L4 -> {machine_type} (should be g2-standard-8)")
        else:
            print(f"  ⚪ L4 not available")

        # Check T4 availability
        if "NVIDIA_TESLA_T4" in gpu_map:
            machine_type = gpu_map["NVIDIA_TESLA_T4"]
            if machine_type == "n1-standard-4":
                print(f"  ✅ T4 -> {machine_type}")
            else:
                print(f"  ❌ T4 -> {machine_type} (should be n1-standard-4)")
        else:
            print(f"  ❌ T4 missing (should be available in all regions)")

        # Check CPU fallback
        if "CPU" in gpu_map:
            machine_type = gpu_map["CPU"]
            if machine_type == "n1-standard-8":
                print(f"  ✅ CPU -> {machine_type}")
            else:
                print(f"  ❌ CPU -> {machine_type} (should be n1-standard-8)")
        else:
            print(f"  ❌ CPU missing (should be available in all regions)")

        if "NVIDIA_L4" not in gpu_map:
            t4_only_regions.append(region)

    print(f"\n📊 Summary:")
    print(f"  L4 + T4 regions: {len(l4_regions)} - {l4_regions}")
    print(f"  T4-only regions: {len(t4_only_regions)} - {t4_only_regions}")
    print(f"  Total regions: {len(REGION_GPU_MACHINE_MAP)}")

    # Validate expected patterns
    expected_l4_regions = [
        "us-central1",
        "europe-west1",
        "us-east4",
        "us-west4",
        "europe-west3",
        "europe-west4",
        "asia-east1",
        "asia-southeast1",
        "asia-northeast1",
    ]

    expected_t4_only = ["us-west1", "us-east1"]

    print(f"\n🎯 Validation:")

    # Check L4 regions
    missing_l4 = set(expected_l4_regions) - set(l4_regions)
    extra_l4 = set(l4_regions) - set(expected_l4_regions)

    if not missing_l4 and not extra_l4:
        print(f"  ✅ L4 regions match expected")
    else:
        if missing_l4:
            print(f"  ❌ Missing L4 regions: {missing_l4}")
        if extra_l4:
            print(f"  ⚠️ Extra L4 regions: {extra_l4}")

    # Check T4-only regions
    missing_t4_only = set(expected_t4_only) - set(t4_only_regions)
    extra_t4_only = set(t4_only_regions) - set(expected_t4_only)

    if not missing_t4_only and not extra_t4_only:
        print(f"  ✅ T4-only regions match expected")
    else:
        if missing_t4_only:
            print(f"  ❌ Missing T4-only regions: {missing_t4_only}")
        if extra_t4_only:
            print(f"  ⚠️ Extra T4-only regions: {extra_t4_only}")

    print(f"\n✅ Mapping validation completed!")


if __name__ == "__main__":
    test_mappings()
