from __future__ import annotations

from vision_service.model_manifest import model_path
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.findings9 import RAW_CLASS_TO_FINDING


CONFIGURED_FINDING_SOURCES = {
    **{code: "findings9" for code in RAW_CLASS_TO_FINDING.values()},
    "IMPACTED_TOOTH": "impacted_tooth",
}


def readiness_snapshot() -> dict:
    model_files = {
        "motor1_fdi": model_path("motor1_fdi").is_file(),
        "findings9": model_path("findings9").is_file(),
        "impacted_tooth": model_path("impacted_tooth").is_file(),
    }

    configured = sorted(CONFIGURED_FINDING_SOURCES)
    runtime_ready = sorted(
        code
        for code, source in CONFIGURED_FINDING_SOURCES.items()
        if model_files.get(source, False)
    )
    missing = sorted(set(FINDING_CATALOG) - set(runtime_ready))

    return {
        "catalog_total": len(FINDING_CATALOG),
        "configured_total": len(configured),
        "runtime_ready_total": len(runtime_ready),
        "configured_codes": configured,
        "runtime_ready_codes": runtime_ready,
        "missing_codes": missing,
        "model_files": model_files,
        "complete": len(runtime_ready) == len(FINDING_CATALOG),
    }
