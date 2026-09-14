import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_derived48():
    catalog = types.ModuleType("vision_service.motors.catalog")
    codes = (
        "SUPERNUMERARY_TOOTH", "RETAINED_PRIMARY_TOOTH", "UNERUPTED_TOOTH",
        "IMPACTED_TOOTH", "IMPACTED_THIRD_MOLAR",
    )
    catalog.FINDING_CATALOG = {code: (code, "test") for code in codes}
    prior = sys.modules.get("vision_service.motors.catalog")
    sys.modules["vision_service.motors.catalog"] = catalog
    try:
        spec = importlib.util.spec_from_file_location("derived48_geometry_test", ROOT / "vision_service" / "derived48.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if prior is None:
            sys.modules.pop("vision_service.motors.catalog", None)
        else:
            sys.modules["vision_service.motors.catalog"] = prior


class GeometryRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_derived48()

    def test_horizontal_third_molar_is_recovered_as_impacted(self):
        teeth = []
        for fdi, x in zip((31, 32, 33, 34, 35, 36, 37), range(20, 160, 20)):
            teeth.append({"fdi": fdi, "bbox": [x, 100, x + 14, 155]})
        teeth.append({
            "fdi": 38,
            "bbox": [170, 112, 235, 145],
            "polygon": [[170, 112], [202, 112], [235, 112], [235, 145], [202, 145], [170, 145]],
        })
        out = self.mod.derive_findings(None, teeth, [], [])
        codes = {(x.get("finding_code"), str(x.get("fdi"))) for x in out}
        self.assertIn(("IMPACTED_TOOTH", "38"), codes)
        self.assertIn(("IMPACTED_THIRD_MOLAR", "38"), codes)

    def test_vertical_third_molar_is_not_called_impacted_by_axis_alone(self):
        tooth = {"polygon": [[10, 10], [20, 10], [20, 30], [20, 50], [10, 50], [10, 30]]}
        self.assertLess(self.mod._polygon_tilt_deg(tooth), 10)


if __name__ == "__main__":
    unittest.main()
