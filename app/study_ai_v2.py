"""Source-grounded final generation for Academic AI V2."""
from __future__ import annotations

import logging
import os
import re
from typing import Iterator

from app.study_ai import STUDY_SYSTEM_PROMPT, StudyAIError, study_provider_error_for_user
from app.study_provider import (
    ProviderTarget,
    StudyProviderError,
    get_provider,
    report_target_failure,
    report_target_success,
    target_available,
)
from app.study_retrieval_v2 import RetrievalResult

logger = logging.getLogger(__name__)


ACADEMIC_V2_MODEL = "gemini-3.5-flash-lite"


def _generation_targets() -> list[ProviderTarget]:
    """Academic V2 uses exactly one generation provider/model; no fallback chain."""
    return [ProviderTarget("gemini", ACADEMIC_V2_MODEL)]


def _prompt(course_title: str, question: str, retrieval: RetrievalResult, history: list[dict] | None = None) -> str:
    context = "\n\n---\n\n".join(retrieval.note_context)
    understood = retrieval.resolved_query or question
    continuation = (
        "Kaynak sorularını kaynak sırasıyla çöz. Kaynakta olmayan soru veya şık üretme. "
        + ("Bu turda yalnız ilk bölüm getirildi; devamının bulunduğunu belirt. " if retrieval.has_more else "")
        if retrieval.retrieval_mode == 'questions_exhaustive' else ""
    )
    return (
        f"Ders: {course_title}\n\nDERS NOTU KANITLARI:\n{context}\n\n"
        "İSTEĞİ YERİNE GETİR:\n"
        "Yorumlanmış isteğin bütün işlemlerini, karşılaştırma taraflarını, koşullarını, "
        "dışlamalarını, sayılarını, birimlerini, adet/zorluk/biçim/uzunluk ve sırasını koru. "
        "Özgün mesajı ve son konuşmayı da dikkate al; önceki cevapları akademik kaynak sayma.\n\n"
        "KAYNAK DESTEĞİNİ DEĞERLENDİR:\n"
        "Bunlar aramayla getirilen aday kaynaklardır. Yerel bir kural motoru sorunun "
        "tamamını desteklediklerini doğrulamış değildir. Her istek ve karşılaştırma "
        "tarafı için yeterli bilgi var mı kontrol et. Desteklenen kısmı cevapla; "
        "desteklenmeyen kısmın kaynak eksiğini açıkça belirt. Eksik başlıklar tamamlama görevi değildir. Eksik bilgiyi kendi "
        "bilginle doldurma veya notların tamamında yokmuş gibi konuşma. "
        "Sen arama/retrieval yapma; verilen kaynakları değerlendir. "
        "'değildir', 'yanlış', 'önerilmez', 'tercih edilmez' gibi negatif ifadeleri tersine çevirme. "
        "'hariç', 'girme', 'bahsetme' gibi dışlamaları negatif bulguya dönüştürme; dışlanan kapsamı cevaba ekleme. "
        "Niteleyicileri koru. Kaynak dışı bilgi ekleme. "
        "Tablo/şekil/görsel yorumunda gerçek kaynak ekini incele; görmediğin şeyi tarif etme. "
        "Kaynak soruları örüntü olarak verilmişse cevaplarını yeni akademik bilgiye kanıt sayma. "
        + ("Ders kapsamı sınırlı temsili parçalardan oluşur; tüm notları okumuş gibi davranma. "
           if retrieval.retrieval_mode == 'coverage' else "")
        + continuation + "\n\n"
        "Sayfa/dosya atıflarını yalnız verilen KANIT/INTERNAL_SOURCE bilgisinden aktar; uydurma.\n\n"
        f"GEMINI'NİN YORUMLADIĞI İSTEK:\n{understood}\n\n"
        f"KULLANICININ ÖZGÜN MESAJI:\n{question}"
    )


def stream_rag_v2(
    course_title: str,
    question: str,
    history: list[dict],
    retrieval: RetrievalResult,
) -> Iterator[str]:
    if retrieval.clarification:
        yield retrieval.clarification
        return
    if (not retrieval.note_context and not retrieval.attachments) or not retrieval.evidence_sufficient:
        yield 'Bu isteği yanıtlayacak kaynak içeriğini henüz eşleştiremedim. Bu, bilginin notlarda bulunmadığı anlamına gelmez.'
        return
    required_attachment_types = {
        item.get("mime_type")
        for item in retrieval.attachments
        if item.get("mime_type")
    }
    prompt = _prompt(course_title, question, retrieval, history)
    last_error: StudyProviderError | None = None
    attempted_api_calls = 0
    candidates = _generation_targets()
    logger.info(
        "Academic AI V2 generation plan. candidates=%s attachments=%s evidence=%s semantic=%s",
        ",".join(f"{item.provider}:{item.model}" for item in candidates),
        len(retrieval.attachments),
        len(retrieval.evidence),
        retrieval.used_semantic_search,
    )

    # Exactly one final-generation call; difficult failures may have spent one
    # separate bounded planning call before reaching this function.
    for target in candidates:
        if attempted_api_calls >= 1:
            break
        if not target_available(target):
            logger.info(
                "Academic AI V2 generation target skipped. provider=%s model=%s reason=unavailable",
                target.provider,
                target.model,
            )
            continue
        emitted = False
        try:
            provider = get_provider(target.provider)
            if required_attachment_types and not all(
                provider.supports_generation_attachment(mime_type)
                for mime_type in required_attachment_types
            ):
                logger.info(
                    "Academic AI V2 generation target skipped. provider=%s model=%s reason=attachment_unsupported",
                    target.provider,
                    target.model,
                )
                continue

            attempted_api_calls += 1
            logger.info(
                "Academic AI V2 generation target selected. provider=%s model=%s api_call=%s",
                target.provider,
                target.model,
                attempted_api_calls,
            )
            clean_history = [
                {
                    **item,
                    "content": re.sub(r"\n?<!--ACADEMIC_Q_CURSOR:\d+:\d+-->", "", item.get("content") or ""),
                }
                for item in history[-8:]
            ]
            for chunk in provider.generate_stream(
                model=target.model,
                system_prompt=STUDY_SYSTEM_PROMPT,
                history=clean_history,
                prompt=prompt,
                attachments=retrieval.attachments,
                temperature=0.22,
                max_output_tokens=7000,
            ):
                if chunk:
                    emitted = True
                    yield chunk
            if not emitted:
                raise StudyProviderError("Akademik AI boş yanıt döndürdü.")
            report_target_success(target)
            if retrieval.retrieval_mode == "questions_exhaustive" and retrieval.has_more and retrieval.evidence:
                # Persisted with the assistant message and consumed only by the
                # server on an explicit "devam" turn; harmless in rendered HTML.
                last = retrieval.evidence[-1]
                yield f"\n<!--ACADEMIC_Q_CURSOR:{last.material_id}:{last.chunk_index}-->"
            return
        except StudyProviderError as exc:
            report_target_failure(target, exc)
            if emitted:
                raise study_provider_error_for_user(exc) from exc
            last_error = exc
            logger.warning(
                "Academic AI V2 generation target failed before output. provider=%s model=%s code=%s",
                target.provider,
                target.model,
                exc.code,
            )

    if last_error is not None:
        raise study_provider_error_for_user(last_error) from last_error
    raise StudyAIError("Akademik AI şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.")


def ask_rag_v2(
    course_title: str,
    question: str,
    history: list[dict],
    retrieval: RetrievalResult,
) -> str:
    return "".join(stream_rag_v2(course_title, question, history, retrieval)).strip()
