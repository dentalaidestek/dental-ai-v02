import unittest

from vision_service.motors.findings9 import normalize_class as normalize_findings9
from vision_service.motors.yolo31 import normalize_class as normalize_yolo31
from vision_service.pipeline import _merge_findings, _release_strong_findings


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

    def test_strong_filling_requires_a_second_motor(self):
        primary = [{"finding_code":"FILLING","confidence":0.91,"bbox":[10,10,40,40],"motor":"findings9"}]
        released, rejected = _release_strong_findings(primary, [])
        self.assertEqual(released, [])
        self.assertEqual(len(rejected), 1)

    def test_tvem_can_confirm_a_strong_filling(self):
        primary = [{"finding_code":"FILLING","confidence":0.91,"bbox":[10,10,40,40],"motor":"findings9"}]
        controls = [{"finding_code":"FILLING","confidence":0.72,"bbox":[12,12,41,41],"motor":"tvem:11diseases"}]
        released, rejected = _release_strong_findings(primary, controls)
        self.assertEqual(rejected, [])
        self.assertEqual(len(released), 1)
        self.assertTrue(released[0]["fusion_supported"])
        self.assertEqual(released[0]["support_motor"], "tvem:11diseases")

    def test_low_confidence_control_does_not_confirm_filling(self):
        primary = [{"finding_code":"FILLING","confidence":0.91,"bbox":[10,10,40,40],"motor":"findings9"}]
        controls = [{"finding_code":"FILLING","confidence":0.12,"bbox":[12,12,41,41],"motor":"yolo31"}]
        released, rejected = _release_strong_findings(primary, controls)
        self.assertEqual(released, [])
        self.assertEqual(len(rejected), 1)

    def test_other_strong_findings_keep_existing_release_policy(self):
        primary = [{"finding_code":"CROWN","confidence":0.88,"bbox":[10,10,40,40],"motor":"findings9"}]
        released, rejected = _release_strong_findings(primary, [])
        self.assertEqual(rejected, [])
        self.assertEqual(len(released), 1)


if __name__ == "__main__":
    unittest.main()
