"""
Unit tests for Vertex AI GPU compatibility mapping
Validates that static mappings align with actual GCP availability
"""

import unittest
import os
from unittest.mock import patch, MagicMock
from vertex_gpu_service import (
    REGION_GPU_MACHINE_MAP,
    discover_gpu_machine_compatibility,
    get_machine_type_for_gpu,
)


class TestGPUCompatibilityMapping(unittest.TestCase):

    def setUp(self):
        """Set up test environment"""
        self.project_id = "test-project"
        self.test_regions = ["us-central1", "us-west1", "us-east1"]

    @patch("googleapiclient.discovery.build")
    @patch("google.auth.default")
    def test_static_mapping_availability(self, mock_auth, mock_build):
        """Test that static mappings correspond to available machine types"""
        # Mock the Compute Engine API responses
        mock_creds = MagicMock()
        mock_auth.return_value = (mock_creds, None)

        mock_compute = MagicMock()
        mock_build.return_value = mock_compute

        # Mock zones response
        mock_compute.zones().list().execute.return_value = {
            "items": [{"name": "us-central1-a"}, {"name": "us-central1-b"}]
        }

        # Mock accelerators response
        mock_compute.acceleratorTypes().list().execute.return_value = {
            "items": [{"name": "nvidia-l4"}, {"name": "nvidia-tesla-t4"}]
        }

        # Mock machine types response
        mock_compute.machineTypes().list().execute.return_value = {
            "items": [
                {"name": "g2-standard-8"},
                {"name": "g2-standard-4"},
                {"name": "n1-standard-4"},
                {"name": "n1-standard-8"},
            ]
        }

        # Test each region in static mapping
        for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
            if region in self.test_regions:  # Only test subset for speed
                compatibility = discover_gpu_machine_compatibility(
                    self.project_id, region
                )

                # Verify L4 mapping
                if "NVIDIA_L4" in gpu_map:
                    expected_machine = gpu_map["NVIDIA_L4"]
                    self.assertEqual(
                        compatibility.get("NVIDIA_L4"),
                        expected_machine,
                        f"L4 mapping mismatch in {region}: expected {expected_machine}, got {compatibility.get('NVIDIA_L4')}",
                    )

                # Verify T4 mapping
                if "NVIDIA_TESLA_T4" in gpu_map:
                    expected_machine = gpu_map["NVIDIA_TESLA_T4"]
                    self.assertEqual(
                        compatibility.get("NVIDIA_TESLA_T4"),
                        expected_machine,
                        f"T4 mapping mismatch in {region}: expected {expected_machine}, got {compatibility.get('NVIDIA_TESLA_T4')}",
                    )

    def test_l4_uses_g2_standard_8(self):
        """Test that L4 GPUs are mapped to g2-standard-8 (not g2-standard-4)"""
        for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
            if "NVIDIA_L4" in gpu_map:
                machine_type = gpu_map["NVIDIA_L4"]
                self.assertEqual(
                    machine_type,
                    "g2-standard-8",
                    f"L4 in {region} should use g2-standard-8, not {machine_type}",
                )

    def test_t4_uses_n1_standard_4(self):
        """Test that T4 GPUs are mapped to n1-standard-4"""
        for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
            if "NVIDIA_TESLA_T4" in gpu_map:
                machine_type = gpu_map["NVIDIA_TESLA_T4"]
                self.assertEqual(
                    machine_type,
                    "n1-standard-4",
                    f"T4 in {region} should use n1-standard-4, not {machine_type}",
                )

    def test_cpu_fallback_available(self):
        """Test that CPU fallback is available in all regions"""
        for region, gpu_map in REGION_GPU_MACHINE_MAP.items():
            self.assertIn("CPU", gpu_map, f"CPU fallback missing in {region}")
            self.assertEqual(
                gpu_map["CPU"],
                "n1-standard-8",
                f"CPU fallback in {region} should be n1-standard-8",
            )

    def test_get_machine_type_for_gpu_fallback(self):
        """Test the machine type lookup with fallback logic"""
        # Test L4 lookup
        machine_type = get_machine_type_for_gpu("us-central1", "NVIDIA_L4")
        self.assertEqual(machine_type, "g2-standard-8")

        # Test T4 lookup
        machine_type = get_machine_type_for_gpu("us-central1", "NVIDIA_TESLA_T4")
        self.assertEqual(machine_type, "n1-standard-4")

        # Test CPU lookup
        machine_type = get_machine_type_for_gpu("us-central1", "CPU")
        self.assertEqual(machine_type, "n1-standard-8")

        # Test unknown GPU type
        machine_type = get_machine_type_for_gpu("us-central1", "UNKNOWN_GPU")
        self.assertIsNone(machine_type)

    def test_all_regions_have_required_mappings(self):
        """Test that all regions have the required GPU mappings"""
        required_regions = [
            "us-central1",
            "us-west1",
            "us-east1",
            "europe-west1",
            "asia-southeast1",
        ]

        for region in required_regions:
            self.assertIn(region, REGION_GPU_MACHINE_MAP, f"Missing region: {region}")

            region_map = REGION_GPU_MACHINE_MAP[region]

            # Check required mappings
            self.assertIn("NVIDIA_L4", region_map, f"Missing L4 mapping in {region}")
            self.assertIn(
                "NVIDIA_TESLA_T4", region_map, f"Missing T4 mapping in {region}"
            )
            self.assertIn("CPU", region_map, f"Missing CPU mapping in {region}")


class TestGPUCompatibilityIntegration(unittest.TestCase):
    """Integration tests that require actual GCP API calls (optional)"""

    def setUp(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "test-project")
        self.skip_integration = not os.getenv("RUN_INTEGRATION_TESTS")

    def test_real_compatibility_discovery(self):
        """Test real compatibility discovery against GCP APIs"""
        if self.skip_integration:
            self.skipTest(
                "Integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)"
            )

        # Test us-central1 as it's most reliable
        compatibility = discover_gpu_machine_compatibility(
            self.project_id, "us-central1"
        )

        # Should have at least CPU fallback
        self.assertIn("CPU", compatibility)

        # If L4 is available, should use g2-standard-8
        if "NVIDIA_L4" in compatibility:
            self.assertEqual(compatibility["NVIDIA_L4"], "g2-standard-8")

        # If T4 is available, should use n1-standard-4
        if "NVIDIA_TESLA_T4" in compatibility:
            self.assertEqual(compatibility["NVIDIA_TESLA_T4"], "n1-standard-4")


if __name__ == "__main__":
    # Run with: python -m pytest test_vertex_gpu_compatibility.py -v
    unittest.main()
