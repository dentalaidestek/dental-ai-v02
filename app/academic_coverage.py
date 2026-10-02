"""Deterministic coverage planning for broad Academic AI study generation."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import json

@dataclass(frozen=True)
class CoverageBucket:
    material_id: int
    section_title: str
    node_ids: tuple[str, ...]
    chunk_ids: tuple[int, ...]
    weight: int
    question_budget: int

@dataclass(frozen=True)
class CoveragePlan:
    requested_count: int
    buckets: tuple[CoverageBucket, ...]
    covered_chunk_ids: tuple[int, ...]

def _largest_remainder(weights: list[int], total: int) -> list[int]:
    if not weights or total <= 0:
        return [0] * len(weights)
    weights = [max(1, int(x)) for x in weights]
    raw = [total * x / sum(weights) for x in weights]
    base = [int(x) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[: total - sum(base)]:
        base[i] += 1
    return base

def build_coverage_plan(rows: list, requested_count: int) -> CoveragePlan:
    """Allocate questions by actual note coverage rather than retrieval rank."""
    grouped = defaultdict(list)
    for row in rows:
        if str(row[6] or "").upper() == "QUESTION":
            continue
        material_id = int(row[1])
        section = str(row[5] or "Bölümsüz").strip() or "Bölümsüz"
        nodes = ()
        if len(row) > 14 and row[14]:
            try:
                nodes = tuple(sorted(set(json.loads(row[14]).get("nodes") or ())))
            except (TypeError, ValueError):
                nodes = ()
        grouped[(material_id, section.casefold(), nodes)].append(row)

    items = []
    for (material_id, _section_key, nodes), members in grouped.items():
        section = str(members[0][5] or "Bölümsüz")
        chunk_ids = tuple(sorted({int(x[0]) for x in members}))
        items.append((material_id, section, nodes, chunk_ids, len(chunk_ids)))
    items.sort(key=lambda x: (x[0], x[1].casefold(), x[3][0] if x[3] else 0))

    count = max(1, min(int(requested_count or 10), 200))
    budgets = _largest_remainder([x[4] for x in items], count)
    buckets = tuple(
        CoverageBucket(mid, section, nodes, chunk_ids, weight, budget)
        for (mid, section, nodes, chunk_ids, weight), budget in zip(items, budgets)
        if budget > 0
    )
    return CoveragePlan(
        requested_count=count,
        buckets=buckets,
        covered_chunk_ids=tuple(sorted({cid for b in buckets for cid in b.chunk_ids})),
    )


@dataclass(frozen=True)
class CoverageLedger:
    planned_questions: int
    generated_questions: int
    remaining_questions: int
    completed_bucket_keys: tuple[str, ...]

def bucket_key(bucket: CoverageBucket) -> str:
    return f"{bucket.material_id}:{bucket.section_title.casefold()}:{'|'.join(bucket.node_ids) or '-'}"

def build_coverage_ledger(plan: CoveragePlan, generated_by_bucket: dict[str, int] | None = None) -> CoverageLedger:
    generated_by_bucket = generated_by_bucket or {}
    completed = []
    generated = 0
    for bucket in plan.buckets:
        key = bucket_key(bucket)
        made = max(0, min(int(generated_by_bucket.get(key, 0)), bucket.question_budget))
        generated += made
        if made >= bucket.question_budget:
            completed.append(key)
    return CoverageLedger(
        planned_questions=plan.requested_count,
        generated_questions=generated,
        remaining_questions=max(0, plan.requested_count - generated),
        completed_bucket_keys=tuple(completed),
    )
