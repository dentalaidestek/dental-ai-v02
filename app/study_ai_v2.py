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
from app.dental_query_intent import classify_dental_intent

logger = logging.getLogger(__name__)


ACADEMIC_V2_MODEL = "gemini-3.5-flash-lite"


def _generation_targets() -> list[ProviderTarget]:
    """Academic V2 uses exactly one generation provider/model; no fallback chain."""
    return [ProviderTarget("gemini", ACADEMIC_V2_MODEL)]


_INTENT_RESPONSE_RULES = {
    "value": "İstenen değeri/ölçümü kanıtta varsa ilk cümlede doğrudan ver; sonra yalnız gerekli bağlamı ekle.",
    "definition": "Önce kısa ve doğrudan tanımı ver; ardından kanıttaki ayırt edici özellikleri ekle.",
    "measurement": "Neyin, nasıl ve hangi referansla ölçüldüğünü kanıtın desteklediği sırayla açıkla.",
    "comparison": "Karşılaştırılan kavramları aynı ölçütler üzerinden yan yana ve tekrar etmeden karşılaştır.",
    "classification": "Sınıflamayı kaynak yapısını bozmadan düzenli ver; sınıf/evre ölçütlerini birbirine karıştırma.",
    "diagnosis": "Tanı, bulgu ve ayırıcı tanı ifadelerini kanıtta nasıl ayrılmışsa öyle tut; yeni tanı çıkarımı yapma.",
    "treatment": "Endikasyon, işlem ve sonuç/izlem bilgisini kanıt destekliyorsa mantıksal sırada birleştir.",
    "complication": "Komplikasyon ile risk/neden/önleme bilgisini kanıtta desteklenen ilişkilerle eşleştir.",
    "cause": "Neden, risk faktörü ve mekanizmayı kanıtta desteklenen neden-sonuç yönünü bozmadan açıkla.",
    "visual": "Yalnız ekli kaynak sayfasında gerçekten görülebilen ve metin kanıtıyla desteklenen özellikleri yorumla.",
}


def _response_contract(question: str) -> str:
    intent = classify_dental_intent(question)
    return _INTENT_RESPONSE_RULES.get(
        intent.name,
        "Sorunun istediği bilgiye doğrudan cevap ver; kanıt dışı ayrıntıyla cevabı genişletme.",
    )


def _prompt(course_title: str, question: str, retrieval: RetrievalResult) -> str:
    context = "\n\n---\n\n".join(retrieval.note_context)
    exhaustive_rule = ""
    if retrieval.retrieval_mode == "questions_exhaustive":
        exhaustive_rule = (
            "Bu istek kaynak içindeki soruları çözme isteğidir. Verilen soru/şıkları kaynak sırasını "
            "koruyarak çöz; soru kökü ile A-E seçeneklerini birbirinden ayırma. Kaynakta görünmeyen "
            "seçenek veya soru uydurma. Her soru için seçtiğin cevabı ve kısa gerekçeyi ver. "
        )
        if retrieval.has_more:
            exhaustive_rule += (
                "Bu turda güvenli bağlam sınırı nedeniyle kaynaktaki soruların yalnız ilk bölümü "
                "verildi; yanıtın sonunda daha fazla soru bulunduğunu açıkça belirt. "
            )
    return (
        f"Ders: {course_title}\n\n"
        "DERS NOTU KANITLARI:\n" + context + "\n\n"
        "CEVAP BİÇİMİ:\n" + _response_contract(question) + "\n\n"
        "KANIT KURALI:\n"
        + exhaustive_rule +
        "Sen arama/retrieval yapma ve kendi genel bilginden yeni akademik bilgi ekleme. "
        "Görevin yalnız sistemin seçtiği kanıtları kullanıcının sorusuna göre seçmek, "
        "birleştirmek ve doğal, anlaşılır bir cevaba dönüştürmektir. Aynı bilgiyi gereksiz "
        "tekrarlama; farklı kanıtlar birbirini tamamlıyorsa anlamını değiştirmeden birleştir. "
        "Kanıtların desteklemediği boşlukları tahmin ederek doldurma. "
        "Yalnız yukarıdaki kanıtlara ve ekli kaynak sayfalarına dayan. Kanıt yetersizse bunu açıkça söyle. "
        "Sayfa ya da dosya adını yalnız kullanıcı kaynak istediğinde, sadece verilen INTERNAL_SOURCE "
        "bilgisinden aktar; uydurma. Tablo/şekil eki varsa metin çıkarımıyla birlikte incele.\n\n"
        f"KULLANICI MESAJI:\n{question.strip()}"
    )


def stream_rag_v2(
    course_title: str,
    question: str,
    history: list[dict],
    retrieval: RetrievalResult,
) -> Iterator[str]:
    if not retrieval.note_context and not retrieval.attachments:
        raise StudyAIError("Bu soruyla ilişkilendirilebilecek ders notu bulunamadı.")
    required_attachment_types = {
        item.get("mime_type")
        for item in retrieval.attachments
        if item.get("mime_type")
    }
    prompt = _prompt(course_title, question, retrieval)
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

    # Exactly one external AI call is allowed for Academic V2.
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
