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
from vision_service.validation_matrix import VALIDATION_TARGETS


# These findings use the already integrated, locally pinned model paths. The
# baseline was validated before the current 48-finding expansion and must not be
# reset simply because the remaining Vision48 findings still need validation.
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
    runtime_ready = sorted(
        code for code, source in PINNED_DIRECT_FINDINGS.items()
        if pinned_files.get(source, False)
    )
    lane_counts = Counter(target.lane for target in VALIDATION_TARGETS.values())
    license_blockers = production_license_blockers()

    return {
        "catalog_total": len(FINDING_CATALOG),
        "implementation_total": len(MOTOR_SPECS),
        "implemented_codes": sorted(MOTOR_SPECS),
        "pinned_direct_configured_total": len(PINNED_DIRECT_FINDINGS),
        "runtime_validated_baseline_total": len(runtime_ready),
        "runtime_validated_baseline_codes": runtime_ready,
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
        "runtime_validation_complete": len(runtime_ready) == len(FINDING_CATALOG),
        "note": (
            "The existing nine-finding baseline and FDI numbering validation are preserved; "
            "only the remaining Vision48 findings require additional runtime validation. "
            "Optional models with non-commercial or unknown licensing remain production blockers."
        ),
    }
