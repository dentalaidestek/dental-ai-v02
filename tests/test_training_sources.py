import unittest

from training.source_catalog import SOURCES, automatic_sources
from training.vision48_specialists import NAMES31, NAMES_Z
from vision_service.motors.catalog import FINDING_CATALOG


class TrainingSourceTests(unittest.TestCase):
    def test_automatic_training_sources_exist(self):
        keys = {s.key for s in automatic_sources()}
        self.assertEqual(keys, {"kaggle31", "zenodo14"})

    def test_specialist_tracks_do_not_retrain_existing_nine_as_outputs(self):
        pinned = {
            "MISSING_TOOTH", "IMPACTED_TOOTH", "FILLING", "CROWN", "BRIDGE",
            "IMPLANT", "ROOT_CANAL_TREATED", "CARIES", "PERIAPICAL_RADIOLUCENCY",
        }
        outputs = set(NAMES31.values()) | set(NAMES_Z.values())
        self.assertFalse(outputs & pinned)

    def test_canonical_specialist_outputs_are_known_findings_or_explicit_helpers(self):
        helpers = {
            "ROOT_RESORPTION_GENERIC", "PRIMARY_TOOTH_HELPER", "MANDIBULAR_CANAL_HELPER",
            "BONE_LOSS_GENERIC", "CYST_HELPER", "BONE_DEFECT_HELPER",
        }
        for name in set(NAMES31.values()) | set(NAMES_Z.values()):
            self.assertTrue(name in FINDING_CATALOG or name in helpers, name)

    def test_rvg_and_caries_sources_cover_hard_missing_labels(self):
        self.assertIn("UNERUPTED_TOOTH", SOURCES["roboflow_rvg18"].target_signals)
        self.assertIn("CALCULUS", SOURCES["roboflow_caries87"].target_signals)
        self.assertIn("UNDERFILLED_ROOT_CANAL", SOURCES["roboflow_caries87"].target_signals)
        self.assertIn("OVERFILLED_ROOT_CANAL", SOURCES["roboflow_caries87"].target_signals)


if __name__ == "__main__":
    unittest.main()
