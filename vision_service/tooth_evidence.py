from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

VALID_MODALITIES = {"PANORAMIC", "PERIAPICAL", "INTRAORAL_PHOTO", "BITEWING"}
REVIEW_STATES = {"unreviewed", "accepted", "rejected", "edited"}


def _fdi(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    q, p = divmod(n, 10)
    return n if q in {1, 2, 3, 4, 5, 6, 7, 8} and 1 <= p <= 8 else None


def _confidence(item: dict[str, Any]) -> float | None:
    value = item.get("confidence", item.get("score"))
    if value is None:
        return None
    try:
        n = float(value)
        if n > 1:
            n /= 100.0
        return max(0.0, min(1.0, n))
    except (TypeError, ValueError):
        return None


def normalize_evidence(item: dict[str, Any], *, modality: str | None = None, source_image_id: str | None = None) -> dict[str, Any]:
    mod = str(item.get("modality") or modality or "").upper().strip()
    if mod not in VALID_MODALITIES:
        mod = "UNKNOWN"
    review = str(item.get("review_state") or "unreviewed").lower().strip()
    if review not in REVIEW_STATES:
        review = "unreviewed"
    tooth = _fdi(item.get("tooth_fdi", item.get("fdi", item.get("tooth"))))
    return {
        "finding_code": str(item.get("finding_code") or item.get("code") or "UNKNOWN_FINDING").strip().upper(),
        "label": str(item.get("label") or item.get("finding") or "Bulgu").strip(),
        "tooth_fdi": tooth,
        "surface": item.get("surface"),
        "modality": mod,
        "source_image_id": item.get("source_image_id") or source_image_id,
        "source_motor": item.get("source_motor"),
        "captured_at": item.get("captured_at"),
        "confidence": _confidence(item),
        "bbox": item.get("bbox"),
        "localization_type": item.get("localization_type"),
        "candidate_only": bool(item.get("candidate_only", False)),
        "review_state": review,
        "clinician_edit": item.get("clinician_edit"),
        "raw": item,
    }


def collect_modal_evidence(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict) or not result.get("ok", True):
            continue
        modality = str(result.get("modality") or "").upper()
        image_id = result.get("source_image_id") or result.get("image_id")
        pools = [result.get("findings", []), result.get("auxiliary_radiographic_findings", []), result.get("image_level_findings", [])]
        for pool in pools:
            if not isinstance(pool, list):
                continue
            for item in pool:
                if isinstance(item, dict):
                    out.append(normalize_evidence(item, modality=modality, source_image_id=image_id))
    return out


def fuse_for_tooth(evidence: Iterable[dict[str, Any]], tooth_fdi: int) -> list[dict[str, Any]]:
    tooth = _fdi(tooth_fdi)
    if tooth is None:
        raise ValueError("Geçersiz FDI diş numarası")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in evidence:
        if ev.get("review_state") == "rejected":
            continue
        # Image-level/unassigned evidence is deliberately NOT guessed onto a tooth.
        if _fdi(ev.get("tooth_fdi")) != tooth:
            continue
        code = str(ev.get("finding_code") or "UNKNOWN_FINDING").upper()
        groups[code].append(ev)

    fused: list[dict[str, Any]] = []
    for code, items in groups.items():
        items = sorted(items, key=lambda x: (x.get("captured_at") or "", x.get("confidence") or -1), reverse=True)
        fused.append({
            "finding_code": code,
            "label": items[0].get("clinician_edit") or items[0].get("label"),
            "tooth_fdi": tooth,
            "supported_by": sorted({x.get("modality") for x in items if x.get("modality")}),
            "evidence_count": len(items),
            "evidence": items,
            # No confidence addition/averaging across independent motors/modalities.
        })
    return sorted(fused, key=lambda x: x["finding_code"])


def build_tooth_evidence_package(*, tooth_fdi: int, modality_results: Iterable[dict[str, Any]], tooth_record: dict[str, Any] | None = None, manual_findings: Iterable[dict[str, Any] | str] = (), clinical_context: dict[str, Any] | None = None) -> dict[str, Any]:
    tooth = _fdi(tooth_fdi)
    if tooth is None:
        raise ValueError("Geçersiz FDI diş numarası")
    all_evidence = collect_modal_evidence(modality_results)
    fused = fuse_for_tooth(all_evidence, tooth)
    manual: list[dict[str, Any]] = []
    for item in manual_findings:
        if isinstance(item, str):
            manual.append({"text": item.strip(), "source": "clinician_manual"})
        elif isinstance(item, dict):
            manual.append({**item, "source": item.get("source", "clinician_manual")})
    unresolved = [x for x in all_evidence if x.get("tooth_fdi") is None and x.get("review_state") != "rejected"]
    return {
        "schema": "dental_ai.tooth_evidence.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tooth_fdi": tooth,
        "tooth_record": tooth_record or {},
        "manual_findings": manual,
        "clinical_context": clinical_context or {},
        "fused_findings": fused,
        "unassigned_image_evidence": unresolved,
        "policy": {
            "rejected_evidence_excluded": True,
            "unassigned_evidence_not_guessed_to_tooth": True,
            "cross_motor_confidence_not_summed": True,
            "preserve_source_and_capture_time": True,
        },
    }
