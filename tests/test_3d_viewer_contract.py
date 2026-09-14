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

    def test_visible_results_are_deduplicated(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("function dedupeFindings", script)
        self.assertIn("function allFindings(){return dedupeFindings", script)
        self.assertIn("const direct=findings.filter", script)
        self.assertIn("displayFindingFamily", script)
        self.assertIn("IMPACTED_THIRD_MOLAR'?'IMPACTED_TOOTH", script)

    def test_reference_canal_is_not_invented_without_signal(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("if(!helper)return 'gösterilmedi: filmden mandibular kanal sinyali yok'", script)
        self.assertIn("addMandibularCanals(scene,mandibleRoot)", script)

    def test_invalid_canal_metrics_are_suppressed(self):
        base = (ROOT / "vision_service" / "templates" / "viewer_v3.js").read_text(encoding="utf-8")
        self.assertIn("curvatureDeg<=90", base)
        self.assertIn("if(path?.reliable)", base)
        self.assertIn("Geçersiz uzunluk/eğrilik değeri gösterilmedi", base)

    def test_occlusion_and_detail_patient_pose_are_applied(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("maxillaRoot.position.z=-2.8", script)
        self.assertIn("mandibleRoot.position.z=2.8", script)
        self.assertIn("pose.rotation.y=transform.rotationY", script)
        self.assertIn("fitCamera(toothScene,group,1.72)", script)

    def test_missing_atlas_tooth_uses_contralateral_fallback(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("function resolveToothPart", script)
        self.assertIn("opposite={1:2,2:1,3:4,4:3}", script)
        self.assertIn("if(mirrorX)mesh.scale.x=-1", script)
        self.assertIn("atlas_fallbacks:atlasFallbacks", script)

    def test_mesh_transforms_cannot_mutate_shared_atlas_buffer(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("new Float32Array(new Float32Array(buffer,part.positions", script)
        self.assertIn("new Uint32Array(new Uint32Array(buffer,part.indices", script)
        self.assertIn("rendered_teeth:renderedTeeth", script)
        self.assertIn("diş 3D'ye yerleştirildi", script)

    def test_horizontal_masks_keep_their_full_impacted_axis(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertIn("if(xx>yy){vx=1;vy=0}", script)
        self.assertIn("-1.45,1.45", script)

    def test_external_atlas_is_revision_pinned(self):
        script = FINAL.read_text(encoding="utf-8")
        self.assertRegex(script, r"const ATLAS_REV='[0-9a-f]{40}'")
        self.assertNotIn("OMFAtlas/main/", script)


if __name__ == "__main__":
    unittest.main()
