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
from app.dental_query_intent import build_dental_requirement_plan

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
    "treatment": "Tedaviyi; endikasyon, işlem ve sonuç/izlem bilgisini kanıt destekliyorsa mantıksal sırada birleştir.",
    "complication": "Komplikasyon ile risk/neden/önleme bilgisini kanıtta desteklenen ilişkilerle eşleştir.",
    "cause": "Neden, risk faktörü ve mekanizmayı kanıtta desteklenen neden-sonuç yönünü bozmadan açıkla.",
    "visual": "Yalnız ekli kaynak sayfasında gerçekten görülebilen ve metin kanıtıyla desteklenen özellikleri yorumla.",
}


def _response_contract(question: str) -> str:
    plan = build_dental_requirement_plan(question)
    names = [item.name for item in plan.intents if item.name != "general"]
    rules = [_INTENT_RESPONSE_RULES[name] for name in names if name in _INTENT_RESPONSE_RULES]
    if not rules:
        rules = ["Sorunun istediği bilgiye doğrudan cevap ver; kanıt dışı ayrıntıyla cevabı genişletme."]
    if len(rules) > 1:
        return (
            "Sorudaki her açık isteği ayrı ayrı karşıla ve hiçbirini atlama. "
            + " ".join(rules)
        )
    return rules[0]

def _prompt(course_title: str, question: str, retrieval: RetrievalResult, history: list[dict] | None = None) -> str:
    from app.academic_dialogue import dialogue_rules
    from app.academic_study_contract import study_output_rules
    context = "\n\n---\n\n".join(retrieval.note_context)
    understood_question = (retrieval.resolved_query or question).strip()
    from app.academic_task_language import elliptical_study_request
    interpreted = retrieval.semantic_planner_attempted
    outline_rule = ''
    if not interpreted and elliptical_study_request(question) == 'outline':
        headings = list(dict.fromkeys(item.section_title for item in retrieval.evidence if item.section_title))
        outline_rule = (
            'Kullanıcı önceki yanıtın kapsamını veya derinliğini yetersiz buldu. '
            'Aşağıdaki kanıtlarda bulunan başlıkları tek bir başlığa indirgeme. '
            'Her başlığı ayrı işle; kanıt destekliyorsa tanımını, mantığını ve önemli '
            'ayrıntılarını açıkla. Önceki yanıtı yalnız tekrar etme. '
            'Kanıt verilmeyen başlıkları açıklanmış veya incelenmiş gibi gösterme. '
            'Tam ders kapsamı sağlanmıyorsa mevcut kapsamın sınırını açıkça belirt. '
            f'Getirilen kanıtların bölüm başlıkları: {", ".join(headings) or "etiketlenmemiş"}.\n\n'
        )
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
        "CEVAP BİÇİMİ:\n" + (
            "Yorumlanmış istekteki bütün işlemleri, karşılaştırma taraflarını, koşulları, dışlamaları ve istenen sırayı koru."
            if interpreted else _response_contract(understood_question)
        ) + "\n\n" + outline_rule +
        "ÇALIŞMA ÇIKTISI:\n" + (
            "İstenen adet, zorluk, biçim ve uzunluğu yorumlanmış istekten uygula; kaynak yeterliliğinin sınırlarını açıkça belirt."
            if interpreted else study_output_rules(understood_question,
                [item.section_title for item in retrieval.evidence if item.section_title])
        ) + "\n\n"
        "ÇALIŞMA ETKİLEŞİMİ:\n" + (
            "Özgün mesajı ve son konuşmayı yorumlanmış istekle birlikte değerlendir. Önceki cevapları akademik kanıt sayma."
            if interpreted else dialogue_rules(question, history)
        ) + "\n\n"
        "KANIT DURUMU:\n"
        f"Retrieval modu: {retrieval.retrieval_mode}. "
        f"Yerel kanıt güveni: {retrieval.evidence_confidence:.2f}. "
        + (
            "Bu mod tüm READY ders indeksinden seçilmiş sınırlı temsili kapsam kanıtıdır; "
            "seçilmeyen bölümleri görmüş gibi davranma. "
            if retrieval.retrieval_mode == "coverage" else ""
        )
        + f"Kapsanan başlıklar: {', '.join(retrieval.covered_facets) or 'doğrudan kanıt'}. "
        f"Eksik başlıklar: {', '.join(retrieval.missing_facets) or 'yok'}. "
        "Eksik başlıklar tamamlama görevi değildir; kanıtta yoksa onları kendi bilginle doldurma.\n\n"
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
        "SORU YÖNÜ KURALI:\n"
        "- 'değildir', 'yanlış', 'önerilmez', 'tercih edilmez' gibi negatif bilgi yönlerini tersine çevirme.\n"
        "- 'hariç', 'girme', 'bahsetme' gibi açık dışlama ifadelerini negatif bulguya dönüştürme; dışlanan kapsamı cevaba ekleme.\n"
        "- Karşılaştırmada adı geçen her tarafı ayrı ayrı kanıta bağla; bir tarafın bilgisini diğerine genelleme.\n"
        "- Çene/yön/diş/akut-kronik gibi niteleyicileri cevap boyunca koru.\n\n"
        f"SİSTEMİN ÇÖZÜMLEDiĞİ SORU:\n{understood_question}\n\n"
        f"KULLANICININ BU TURDAKİ MESAJI:\n{question.strip()}"
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
        from app.academic_dialogue import evidence_followup
        yield evidence_followup(
            resolved_query=retrieval.resolved_query or question,
            retrieval_mode=retrieval.retrieval_mode,
            has_evidence=bool(retrieval.note_context or retrieval.attachments),
            missing_facets=retrieval.missing_facets,
        )
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
