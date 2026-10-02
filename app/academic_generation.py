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

    @property
    def work_units(self) -> int:
        return self.question_count

def plan_generation_batches(plan: CoveragePlan, max_questions_per_batch: int = 10, max_chunks_per_batch: int = 10, generated_by_bucket: dict[str, int] | None = None) -> tuple[GenerationBatch, ...]:
    """Split coverage budgets into bounded batches without touching normal QA."""
    qcap = max(1, min(int(max_questions_per_batch), 12))
    generated_by_bucket = generated_by_bucket or {}
    ccap = max(1, min(int(max_chunks_per_batch), 20))
    batches = []
    for bucket in plan.buckets:
        already = max(0, min(int(generated_by_bucket.get(bucket_key(bucket), 0)), bucket.question_budget))
        remaining = bucket.question_budget - already
        chunks = bucket.chunk_ids or ()
        offset = already % max(1, len(chunks))
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


def hydration_windows(batches: tuple[GenerationBatch, ...], max_unique_chunks: int = 32) -> tuple[tuple[int, ...], ...]:
    """Coalesce adjacent batch evidence into bounded DB hydration windows."""
    cap = max(1, min(int(max_unique_chunks), 48))
    windows = []
    current = []
    seen = set()
    for batch in batches:
        needed = [cid for cid in batch.chunk_ids if cid not in seen]
        if current and len(current) + len(needed) > cap:
            windows.append(tuple(current))
            current = []
            seen = set()
            needed = list(batch.chunk_ids)
        for cid in needed:
            if cid not in seen and len(current) < cap:
                current.append(cid)
                seen.add(cid)
    if current:
        windows.append(tuple(current))
    return tuple(windows)


_ACADEMIC_OUTPUT_CONTRACTS = {
    "summarize": (
        "Kanıtları bölüm ve alt konu bütünlüğünü koruyarak özetle. Temel tanım, ölçüm, "
        "sınıflama, bulgu, endikasyon, tedavi ve komplikasyonlardan kaynakta bulunanları "
        "atlama; aynı bilgiyi tekrar etme."
    ),
    "explain": (
        "Konuyu öğretici sırayla açıkla: temel kavramdan ilişkilere ilerle. Yalnız kanıtta "
        "bulunan neden-sonuç, anatomi, ölçüm, sınıflama, tanı ve tedavi ilişkilerini kur."
    ),
    "exam_points": (
        "Yalnız not kanıtından sınav değeri taşıyan noktaları çıkar; sayı, sınıflama, "
        "ayırt edici bulgu ve ilişkileri kaynak desteği olmadan önem sırasına koyma."
    ),
    "comparison": (
        "Karşılaştırılan kavramları ortak ölçütler altında düzenle; bir tarafta kanıt "
        "olmayan özelliği diğer taraftan tahmin ederek tamamlama."
    ),
    "generate_questions": (
        "Yalnız verilen kanıttan doğrulanabilir sorular ve cevaplar üret; tekrar etme."
    ),
}

def academic_batch_contract(task: str, batch: GenerationBatch) -> str:
    rule = _ACADEMIC_OUTPUT_CONTRACTS.get(
        task,
        "Kullanıcının akademik görevini yalnız verilen kanıtlarla yerine getir; kanıt dışı bilgi ekleme.",
    )
    concepts = ", ".join(batch.node_ids) if batch.node_ids else "bölümdeki kaynak kavramları"
    return (
        f"Görev: {task}\\nBölüm: {batch.section_title}\\n"
        f"Kanıt kapsamı: {concepts}\n{rule}\n"
        "Bu yalnız bir coverage parçasıdır. Diğer bölümlerde ele alınacak bilgileri "
        "uydurup bu parçaya ekleme; bu parçanın kanıtını eksiksiz ve tekrar etmeden işle."
    )
