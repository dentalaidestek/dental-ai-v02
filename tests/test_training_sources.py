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

    def test_new_research_candidates_are_not_automatic_training_sources(self):
        research_keys = {
            "roboflow_apex_resorption",
            "roboflow_lamina_pdl",
            "roboflow_furcation_detection",
            "roboflow_tmj_morphology",
        }
        self.assertTrue(research_keys <= set(SOURCES))
        automatic = {s.key for s in automatic_sources()}
        self.assertFalse(research_keys & automatic)
        for key in research_keys:
            self.assertEqual(SOURCES[key].access, "hosted_model_or_export_required")

    def test_generic_resorption_candidate_does_not_invent_internal_external_subtypes(self):
        signals = set(SOURCES["roboflow_apex_resorption"].target_signals)
        self.assertIn("ROOT_RESORPTION_GENERIC", signals)
        self.assertNotIn("EXTERNAL_ROOT_RESORPTION", signals)
        self.assertNotIn("INTERNAL_ROOT_RESORPTION", signals)

    def test_tmj_research_source_remains_helper_only(self):
        signals = set(SOURCES["roboflow_tmj_morphology"].target_signals)
        self.assertEqual(signals, {"TMJ_MORPHOLOGY_HELPER"})
        self.assertNotIn("CONDYLAR_FLATTENING", signals)
        self.assertNotIn("CONDYLAR_EROSION", signals)

    def test_lamina_pdl_candidate_names_exact_targets_but_is_not_pass_evidence(self):
        signals = set(SOURCES["roboflow_lamina_pdl"].target_signals)
        self.assertIn("LOSS_OF_LAMINA_DURA", signals)
        self.assertIn("WIDENED_PDL", signals)
        self.assertIn("FURCATION_BONE_LOSS", signals)
        self.assertNotEqual(SOURCES["roboflow_lamina_pdl"].access, "automatic_http")
        self.assertNotEqual(SOURCES["roboflow_lamina_pdl"].access, "automatic_kagglehub")


if __name__ == "__main__":
    unittest.main()
