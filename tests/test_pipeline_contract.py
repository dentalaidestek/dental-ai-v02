import unittest

from vision_service.motors.findings9 import normalize_class as normalize_findings9
from vision_service.motors.yolo31 import normalize_class as normalize_yolo31
from vision_service.pipeline import _merge_findings


class PipelineContractTests(unittest.TestCase):
    def test_findings9_auxiliary_is_preserved_as_signal(self):
        self.assertEqual(normalize_findings9("Wisdom Tooth")["signal"], "WISDOM_TOOTH_PRESENT")

    def test_yolo31_helper_is_not_promoted_to_canonical_disease(self):
        value = normalize_yolo31("Bone Loss")
        self.assertEqual(value["type"], "helper")
        self.assertEqual(value["signal"], "BONE_LOSS_GENERIC")

    def test_dedupe_keeps_stronger_same_fdi_prediction(self):
        items = [
            {"finding_code":"CARIES","confidence":0.9,"bbox":[1,1,10,10],"fdi":36,"motor":"a"},
            {"finding_code":"CARIES","confidence":0.6,"bbox":[2,2,11,11],"fdi":36,"motor":"b"},
        ]
        result = _merge_findings(items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["motor"], "a")
        self.assertIn("b", result[0].get("supporting_motors", []))


if __name__ == "__main__":
    unittest.main()
