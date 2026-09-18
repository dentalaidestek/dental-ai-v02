import unittest

from vision_service.derived48 import derive_findings


class DerivedMotorTests(unittest.TestCase):
    def codes(self, result):
        return {x["finding_code"] for x in result}

    def test_impacted_third_molar_composition(self):
        findings = [{"finding_code":"IMPACTED_TOOTH","confidence":0.9,"bbox":[10,10,30,40],"fdi":38}]
        result = derive_findings(None, [{"fdi":38,"bbox":[10,10,30,40]}], findings, [])
        self.assertIn("IMPACTED_THIRD_MOLAR", self.codes(result))

    def test_implant_supported_crown_composition(self):
        findings = [
            {"finding_code":"IMPLANT","confidence":0.91,"bbox":[10,20,30,70],"fdi":36},
            {"finding_code":"CROWN","confidence":0.88,"bbox":[9,8,31,28],"fdi":36},
        ]
        result = derive_findings(None, [{"fdi":36,"bbox":[8,8,32,72]}], findings, [])
        self.assertIn("IMPLANT_SUPPORTED_CROWN", self.codes(result))

    def test_recurrent_caries_composition(self):
        findings = [
            {"finding_code":"CARIES","confidence":0.8,"bbox":[10,10,20,20],"fdi":26},
            {"finding_code":"FILLING","confidence":0.9,"bbox":[12,12,25,24],"fdi":26},
        ]
        result = derive_findings(None, [{"fdi":26,"bbox":[5,5,30,50]}], findings, [])
        self.assertIn("RECURRENT_CARIES", self.codes(result))

    def test_mandibular_canal_proximity_composition(self):
        helpers = [{"signal":"MANDIBULAR_CANAL_HELPER","confidence":0.9,"bbox":[10,50,100,65]}]
        teeth = [{"fdi":38,"bbox":[65,20,85,55]}]
        result = derive_findings(None, teeth, [], helpers)
        self.assertIn("MANDIBULAR_CANAL_PROXIMITY", self.codes(result))

    def test_orthodontic_union(self):
        helpers = [{"signal":"ORTHODONTIC_APPLIANCE_HELPER","confidence":0.8,"bbox":[1,2,3,4],"raw_class":"Wire"}]
        result = derive_findings(None, [], [], helpers)
        self.assertIn("ORTHODONTIC_APPLIANCE", self.codes(result))


if __name__ == "__main__":
    unittest.main()
