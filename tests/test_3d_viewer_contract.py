import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "vision_service" / "templates" / "viewer_v3.html"
FINAL = ROOT / "vision_service" / "templates" / "viewer_v3_finalfix.js"


class Viewer3DContractTests(unittest.TestCase):
    def test_only_one_renderer_override_layer_is_loaded(self):
        html = HTML.read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="([^"]+viewer-v3[^"]*)"', html)
        self.assertEqual(scripts, ["/viewer-v3.js", "/viewer-v3-finalfix.js"])
        self.assertNotIn("viewer-v3-patch.js", html)
        self.assertNotIn("viewer-v3-enhance.js", html)
        self.assertNotIn("viewer-v3-realjaw.js", html)

    def test_panorama_limits_are_explicit(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("panoramic_conditioned_reference", script)
        self.assertIn("diagnostic:false", script)
        self.assertIn("medical_volume:false", script)
        self.assertIn("patient_specific_depth:false", script)
        self.assertIn("bukkolingual derinlik anatomik referanstır", script)

    def test_patient_cues_and_reference_canal_are_present(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("function patientTransform", script)
        self.assertIn("IMPACTED_CODES", script)
        self.assertIn("function addMandibularCanals", script)
        self.assertIn("MANDIBULAR_CANAL_HELPER", script)
        self.assertIn("BONE_LOSS_RE", script)

    def test_external_atlas_is_revision_pinned(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertRegex(script, r"const ATLAS_REV='[0-9a-f]{40}'")
        self.assertNotIn("OMFAtlas/main/", script)


if __name__ == "__main__":
    unittest.main()
