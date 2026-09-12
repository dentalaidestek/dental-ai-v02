import unittest

from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.readiness import PINNED_DIRECT_FINDINGS, readiness_snapshot
from vision_service.runtime_validation import (
    RUNTIME_VALIDATION_RECORDS,
    RuntimeValidationRecord,
    passes_runtime_contract,
    runtime_pass_codes,
)


class RuntimeValidationTests(unittest.TestCase):
    def test_ledger_covers_all_48_findings(self):
        self.assertEqual(set(RUNTIME_VALIDATION_RECORDS), set(FINDING_CATALOG))
        self.assertEqual(len(RUNTIME_VALIDATION_RECORDS), 48)

    def test_model_availability_is_not_runtime_pass(self):
        snap = readiness_snapshot()
        self.assertEqual(snap["pinned_direct_configured_total"], 9)
        self.assertEqual(len(PINNED_DIRECT_FINDINGS), 9)
        self.assertEqual(snap["runtime_validation_pass_total"], 0)
        self.assertEqual(runtime_pass_codes(), [])
        self.assertFalse(snap["runtime_validation_complete"])

    def test_pass_requires_every_acceptance_field(self):
        base = dict(
            code="CARIES",
            status="pass",
            engine_evidence=("weight:sha256:example",),
            exact_mapping_verified=True,
            positive_cases=("positive_panorama_001",),
            negative_cases=("negative_panorama_001",),
            threshold=0.35,
            fdi_required=True,
            fdi_checked=True,
            fail_isolation_checked=True,
        )
        self.assertTrue(passes_runtime_contract(RuntimeValidationRecord(**base)))

        required_fields = (
            "engine_evidence",
            "exact_mapping_verified",
            "positive_cases",
            "negative_cases",
            "threshold",
            "fdi_required",
            "fdi_checked",
            "fail_isolation_checked",
        )
        replacements = {
            "engine_evidence": (),
            "exact_mapping_verified": False,
            "positive_cases": (),
            "negative_cases": (),
            "threshold": None,
            "fdi_required": None,
            "fdi_checked": False,
            "fail_isolation_checked": False,
        }
        for field in required_fields:
            candidate = dict(base)
            candidate[field] = replacements[field]
            with self.subTest(field=field):
                self.assertFalse(
                    passes_runtime_contract(RuntimeValidationRecord(**candidate))
                )

    def test_fdi_check_may_be_explicitly_not_required(self):
        record = RuntimeValidationRecord(
            code="MAXILLARY_SINUS_OPACIFICATION",
            status="pass",
            engine_evidence=("algorithm:validated_sinus_mask_geometry",),
            exact_mapping_verified=True,
            positive_cases=("positive_panorama_sinus_001",),
            negative_cases=("negative_panorama_sinus_001",),
            threshold=0.50,
            fdi_required=False,
            fdi_checked=False,
            fail_isolation_checked=True,
        )
        self.assertTrue(passes_runtime_contract(record))


if __name__ == "__main__":
    unittest.main()
