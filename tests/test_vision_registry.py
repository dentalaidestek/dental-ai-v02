import unittest

from vision_service.model_manifest import MODEL_ASSETS
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.readiness import CONFIGURED_FINDING_SOURCES


class VisionRegistryTests(unittest.TestCase):
    def test_catalog_is_exactly_48(self):
        self.assertEqual(len(FINDING_CATALOG), 48)

    def test_configured_findings_are_real_catalog_codes(self):
        self.assertTrue(CONFIGURED_FINDING_SOURCES)
        self.assertTrue(set(CONFIGURED_FINDING_SOURCES).issubset(FINDING_CATALOG))

    def test_current_configured_coverage_is_nine(self):
        self.assertEqual(len(CONFIGURED_FINDING_SOURCES), 9)

    def test_model_assets_have_pinned_sha256(self):
        self.assertEqual(set(MODEL_ASSETS), {"motor1_fdi", "findings9", "impacted_tooth"})
        for spec in MODEL_ASSETS.values():
            digest = spec["sha256"]
            self.assertEqual(len(digest), 64)
            int(digest, 16)


if __name__ == "__main__":
    unittest.main()
