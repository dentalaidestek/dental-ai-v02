import unittest

from vision_service.model_manifest import MODEL_ASSETS
from vision_service.model_sources import OPTIONAL_MODEL_SOURCES
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.liodon3 import RAW_TO_CANONICAL as LIODON3_TO_CANONICAL
from vision_service.motors.registry48 import MOTOR_SPECS
from vision_service.motors.tvem import TVEM11_TO_CANONICAL, TVEM_ANATOMY_TO_HELPER
from vision_service.motors.yolo31 import RAW_TO_CANONICAL, RAW_TO_HELPER
from vision_service.readiness import PINNED_DIRECT_FINDINGS, readiness_snapshot
from vision_service.validation_matrix import VALIDATION_TARGETS, by_lane


class VisionRegistryTests(unittest.TestCase):
    def test_catalog_is_exactly_48(self):
        self.assertEqual(len(FINDING_CATALOG), 48)

    def test_every_catalog_finding_has_an_implemented_motor_strategy(self):
        self.assertEqual(set(MOTOR_SPECS), set(FINDING_CATALOG))
        self.assertEqual(len(MOTOR_SPECS), 48)
        for spec in MOTOR_SPECS.values():
            self.assertNotIn(spec.strategy, {"placeholder", "todo", "unknown"})
            self.assertTrue(spec.sources)
            self.assertTrue(spec.description)

    def test_validation_matrix_covers_every_finding_exactly_once(self):
        self.assertEqual(set(VALIDATION_TARGETS), set(FINDING_CATALOG))
        self.assertEqual(len(VALIDATION_TARGETS), 48)
        allowed = {"pinned_direct", "ready_candidate", "composed_candidate", "train_required"}
        self.assertTrue(all(target.lane in allowed for target in VALIDATION_TARGETS.values()))
        self.assertEqual(len(by_lane("pinned_direct")), 9)
        self.assertGreater(len(by_lane("train_required")), 0)
        for target in VALIDATION_TARGETS.values():
            self.assertTrue(target.primary_sources)
            self.assertTrue(target.note)

    def test_pinned_baseline_is_nine_and_not_misreported_as_48(self):
        self.assertEqual(len(PINNED_DIRECT_FINDINGS), 9)
        snap = readiness_snapshot()
        self.assertTrue(snap["implementation_complete"])
        self.assertEqual(snap["implementation_total"], 48)
        self.assertFalse(snap["runtime_validation_complete"])

    def test_pinned_assets_have_sha256(self):
        self.assertEqual(set(MODEL_ASSETS), {"motor1_fdi", "findings9", "impacted_tooth"})
        for spec in MODEL_ASSETS.values():
            digest = spec["sha256"]
            self.assertEqual(len(digest), 64)
            int(digest, 16)

    def test_optional_sources_have_real_locations(self):
        self.assertGreaterEqual(len(OPTIONAL_MODEL_SOURCES), 9)
        for key, source in OPTIONAL_MODEL_SOURCES.items():
            self.assertEqual(key, source.key)
            self.assertTrue(source.repo_candidates)
            self.assertTrue(source.filename)
            self.assertTrue(source.local_name)
        self.assertIn("liodon-ai/dental-panoramic-detector", OPTIONAL_MODEL_SOURCES["liodon3"].repo_candidates)
        self.assertIn("chemahc94/dental-periapical", OPTIONAL_MODEL_SOURCES["panoreader_periapical"].repo_candidates)

    def test_known_ready_model_labels_map_without_class0_guessing(self):
        self.assertEqual(TVEM11_TO_CANONICAL["Deep Caries"], "DEEP_CARIES")
        self.assertEqual(TVEM11_TO_CANONICAL["Residual Root"], "RESIDUAL_ROOT")
        self.assertEqual(TVEM11_TO_CANONICAL["Pontic"], "PONTIC")
        self.assertEqual(TVEM_ANATOMY_TO_HELPER["Mandibular Canal"], "MANDIBULAR_CANAL_HELPER")
        self.assertEqual(TVEM_ANATOMY_TO_HELPER["Maxillary Sinus"], "MAXILLARY_SINUS_HELPER")
        self.assertEqual(RAW_TO_CANONICAL["Post-core"], "ENDO_POST")
        self.assertEqual(RAW_TO_HELPER["Root resorption"], "ROOT_RESORPTION_GENERIC")
        self.assertEqual(LIODON3_TO_CANONICAL["caries"], "CARIES")
        self.assertEqual(LIODON3_TO_CANONICAL["periapical_lesion"], "PERIAPICAL_RADIOLUCENCY")
        self.assertEqual(LIODON3_TO_CANONICAL["impacted_tooth"], "IMPACTED_TOOTH")


if __name__ == "__main__":
    unittest.main()
