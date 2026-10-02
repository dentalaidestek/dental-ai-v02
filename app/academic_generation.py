"""Batch orchestration primitives for broad Academic AI question generation."""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.academic_coverage import CoveragePlan, bucket_key

@dataclass(frozen=True)
class GenerationBatch:
    bucket_key: str
    material_id: int
    section_title: str
    node_ids: tuple[str, ...]
    chunk_ids: tuple[int, ...]
    question_count: int

def plan_generation_batches(plan: CoveragePlan, max_questions_per_batch: int = 8, max_chunks_per_batch: int = 12) -> tuple[GenerationBatch, ...]:
    """Split coverage budgets into bounded batches without touching normal QA."""
    qcap = max(1, min(int(max_questions_per_batch), 12))
    ccap = max(1, min(int(max_chunks_per_batch), 20))
    batches = []
    for bucket in plan.buckets:
        remaining = bucket.question_budget
        chunks = bucket.chunk_ids or ()
        offset = 0
        while remaining > 0:
            qcount = min(qcap, remaining)
            if chunks:
                selected = tuple(chunks[(offset + i) % len(chunks)] for i in range(min(ccap, len(chunks))))
                offset = (offset + len(selected)) % len(chunks)
            else:
                selected = ()
            batches.append(GenerationBatch(
                bucket_key(bucket), bucket.material_id, bucket.section_title,
                bucket.node_ids, selected, qcount,
            ))
            remaining -= qcount
    return tuple(batches)

def question_signature(text: str) -> str:
    clean = re.sub(r"(?mi)^\s*[A-E][.)].*$", " ", text or "")
    clean = re.sub(r"\b\d+[.,]?\d*\b", " # ", clean.casefold())
    clean = re.sub(r"[^a-zçğıöşü#]+", " ", clean)
    return " ".join(clean.split())

def dedupe_generated_questions(questions: list[str]) -> list[str]:
    """Exact/near-lexical guard; semantic grounding remains evidence-driven."""
    kept = []
    signatures = []
    for question in questions:
        sig = question_signature(question)
        if not sig:
            continue
        tokens = set(sig.split())
        duplicate = False
        for old in signatures:
            old_tokens = set(old.split())
            union = tokens | old_tokens
            if sig == old or (union and len(tokens & old_tokens) / len(union) >= 0.88):
                duplicate = True
                break
        if not duplicate:
            kept.append(question)
            signatures.append(sig)
    return kept


def generation_batch_contract(batch: GenerationBatch, difficulty: str | None = None, question_types: tuple[str, ...] = ()) -> str:
    kinds = ", ".join(question_types) if question_types else "kaynağa uygun karışık"
    level = difficulty or "kaynağın düzeyine uygun"
    concepts = ", ".join(batch.node_ids) if batch.node_ids else "bu bölümdeki kanıtlanabilir kavramlar"
    return (
        f"Bölüm: {batch.section_title}\n"
        f"Hedef soru sayısı: {batch.question_count}\n"
        f"Zorluk: {level}\n"
        f"Soru türü: {kinds}\n"
        f"Öncelikli kavramlar: {concepts}\n"
        "Yalnız verilen ders notu kanıtlarından soru üret. Her sorunun cevabı verilen "
        "kanıtta doğrulanabilir olmalı. Kaynakta bulunmayan akademik bilgiyi genel "
        "bilginden ekleme. Aynı bilgiyi yalnız kelimelerini değiştirerek ikinci soru "
        "olarak üretme. Çıkmış soru örnekleri verilmişse yalnız konu, beceri, zorluk "
        "ve biçim örüntüsünü kullan; onların cevabını factual kaynak kabul etme."
    )
