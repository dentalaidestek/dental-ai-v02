from __future__ import annotations

from dataclasses import dataclass

from vision_service.motors.catalog import FINDING_CATALOG


@dataclass(frozen=True)
class RuntimeValidationRecord:
    """Version-controlled runtime acceptance evidence for one panoramic finding.

    A configured model file, implemented heuristic or successful import is not a
    runtime PASS. PASS is intentionally stricter and requires executable evidence,
    exact mapping, positive and negative panorama cases, an explicit threshold,
    fail-isolation verification, and an explicit FDI-localization decision.
    """

    code: str
    status: str = "pending"  # pending | pass | fail
    engine_evidence: tuple[str, ...] = ()
    exact_mapping_verified: bool = False
    positive_cases: tuple[str, ...] = ()
    negative_cases: tuple[str, ...] = ()
    threshold: float | None = None
    fdi_required: bool | None = None
    fdi_checked: bool = False
    fail_isolation_checked: bool = False
    note: str = ""


def passes_runtime_contract(record: RuntimeValidationRecord) -> bool:
    """Return True only when every required runtime-acceptance field is proven."""

    if record.status != "pass":
        return False
    if not record.engine_evidence or not record.exact_mapping_verified:
        return False
    if not record.positive_cases or not record.negative_cases:
        return False
    if record.threshold is None or not (0.0 <= float(record.threshold) <= 1.0):
        return False
    if record.fdi_required is None:
        return False
    if record.fdi_required and not record.fdi_checked:
        return False
    if not record.fail_isolation_checked:
        return False
    return True


# IMPORTANT:
# Keep every finding pending until real panorama fixtures are executed. In
# particular, the nine pinned real-weight baseline findings are *available* but
# are not automatically runtime-validated merely because their weight files are
# present. Replace individual records with evidence-bearing PASS records only
# after positive + negative validation has actually been performed.
RUNTIME_VALIDATION_RECORDS = {
    code: RuntimeValidationRecord(code=code)
    for code in FINDING_CATALOG
}


assert len(RUNTIME_VALIDATION_RECORDS) == 48
assert set(RUNTIME_VALIDATION_RECORDS) == set(FINDING_CATALOG)
assert all(record.status in {"pending", "pass", "fail"} for record in RUNTIME_VALIDATION_RECORDS.values())


def runtime_pass_codes() -> list[str]:
    return sorted(
        code
        for code, record in RUNTIME_VALIDATION_RECORDS.items()
        if passes_runtime_contract(record)
    )


def runtime_pending_codes() -> list[str]:
    passed = set(runtime_pass_codes())
    return sorted(code for code in FINDING_CATALOG if code not in passed)
