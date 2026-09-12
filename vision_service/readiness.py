from __future__ import annotations

from collections import Counter

from vision_service.model_manifest import model_path
from vision_service.model_sources import (
    OPTIONAL_MODEL_SOURCES,
    optional_model_path,
    production_license_blockers,
)
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.findings9 import RAW_CLASS_TO_FINDING
from vision_service.motors.registry48 import MOTOR_SPECS
from vision_service.runtime_validation import runtime_pass_codes, runtime_pending_codes
from vision_service.validation_matrix import VALIDATION_TARGETS


# These findings have already integrated, locally pinned model paths. Availability
# is deliberately separated from runtime validation: a weight file on disk is not
# a positive/negative panorama PASS.
PINNED_DIRECT_FINDINGS = {
    **{code: "findings9" for code in RAW_CLASS_TO_FINDING.values()},
    "IMPACTED_TOOTH": "impacted_tooth",
}


def readiness_snapshot() -> dict:
    pinned_files = {
        "motor1_fdi": model_path("motor1_fdi").is_file(),
        "findings9": model_path("findings9").is_file(),
        "impacted_tooth": model_path("impacted_tooth").is_file(),
    }
    optional_files = {key: optional_model_path(key).is_file() for key in OPTIONAL_MODEL_SOURCES}
    available_baseline = sorted(
        code
        for code, source in PINNED_DIRECT_FINDINGS.items()
        if pinned_files.get(source, False)
    )
    validated = runtime_pass_codes()
    pending = runtime_pending_codes()
    validated_pinned = sorted(set(validated) & set(PINNED_DIRECT_FINDINGS))
    lane_counts = Counter(target.lane for target in VALIDATION_TARGETS.values())
    license_blockers = production_license_blockers()

    return {
        "catalog_total": len(FINDING_CATALOG),
        "implementation_total": len(MOTOR_SPECS),
        "implemented_codes": sorted(MOTOR_SPECS),
        "pinned_direct_configured_total": len(PINNED_DIRECT_FINDINGS),
        "runtime_available_baseline_total": len(available_baseline),
        "runtime_available_baseline_codes": available_baseline,
        # Kept for callers that already consume these fields, but now the names
        # mean what they say: only evidence-backed PASS records are counted.
        "runtime_validated_baseline_total": len(validated_pinned),
        "runtime_validated_baseline_codes": validated_pinned,
        "runtime_validation_pass_total": len(validated),
        "runtime_validation_pass_codes": validated,
        "runtime_validation_pending_total": len(pending),
        "runtime_validation_pending_codes": pending,
        "pinned_model_files": pinned_files,
        "optional_model_files": optional_files,
        "optional_production_license_blockers": license_blockers,
        "optional_production_license_clear": not license_blockers,
        "validation_lane_counts": dict(sorted(lane_counts.items())),
        "training_required_codes": sorted(
            code for code, target in VALIDATION_TARGETS.items()
            if target.lane == "train_required"
        ),
        "ready_candidate_codes": sorted(
            code for code, target in VALIDATION_TARGETS.items()
            if target.lane == "ready_candidate"
        ),
        "composed_candidate_codes": sorted(
            code for code, target in VALIDATION_TARGETS.items()
            if target.lane == "composed_candidate"
        ),
        "implementation_complete": set(MOTOR_SPECS) == set(FINDING_CATALOG),
        "runtime_validation_complete": len(validated) == len(FINDING_CATALOG),
        "note": (
            "implementation/model-file availability is not a clinical/runtime PASS; "
            "runtime PASS requires explicit executable evidence, exact mapping, "
            "positive+negative panorama cases, threshold, FDI decision and fail isolation. "
            "Optional models with non-commercial or unknown licensing remain production blockers."
        ),
    }
