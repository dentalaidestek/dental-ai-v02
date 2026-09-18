import unittest
from vision_service.motors.step1 import adapt_predictions, normalize_class, RAW_TO_CANONICAL
from vision_service.motors.catalog import FINDING_CATALOG

class Step1AdapterTests(unittest.TestCase):
    def test_named_mapping_targets_exist(self):
        for raw, code in RAW_TO_CANONICAL.items():
            with self.subTest(raw=raw):
                self.assertIn(code, FINDING_CATALOG)
                self.assertEqual(normalize_class(raw)['finding_code'], code)

    def test_generic_labels_are_not_diagnoses(self):
        for raw in ['Periodontal bone loss','Germ','Decidious teeth','Lesion','Furcation lesion','Apical lesion']:
            with self.subTest(raw=raw): self.assertEqual(normalize_class(raw)['type'],'helper')
        self.assertEqual(normalize_class('class_0')['type'],'unknown')
        self.assertEqual(normalize_class('46')['type'],'unknown')

    def test_prediction_geometry_threshold_and_rejection(self):
        p={'class':'Root fracture','x':100,'y':120,'width':20,'height':40,'confidence':.8}
        f,h,r=adapt_predictions({'predictions':[p,{**p,'confidence':.1},{**p,'width':-2},{**p,'class':'unknown'},{**p,'x':float('nan')}]}, threshold=.5)
        self.assertEqual(len(f),1); self.assertEqual(f[0]['bbox'],[90,100,110,140])
        self.assertEqual(f[0]['validation_status'],'CANDIDATE_NOT_VALIDATED')
        self.assertFalse(h); self.assertEqual(len(r),3)

    def test_empty_predictions_and_bad_threshold(self):
        self.assertEqual(adapt_predictions({'predictions':[]},threshold=.5),([],[],[]))
        with self.assertRaises(ValueError): adapt_predictions({},threshold=float('nan'))
