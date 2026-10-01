"""Source-grounded final generation for Academic AI V2."""
from __future__ import annotations

import logging
import os
from typing import Iterator

from app.study_ai import STUDY_SYSTEM_PROMPT, StudyAIError, study_provider_error_for_user
from app.study_provider import (
    ProviderTarget,
    StudyProviderError,
    get_generation_targets,
    get_provider,
    report_target_failure,
    report_target_success,
    target_available,
)
from app.study_retrieval_v2 import RetrievalResult

logger = logging.getLogger(__name__)


def _model() -> str:
    return (os.getenv("STUDY_V2_GEMINI_MODEL") or "gemini-3.8-flash").strip()


def _generation_targets() -> list[ProviderTarget]:
    """Keep V2 retrieval fixed while allowing one bounded generation fallback."""
    primary = ProviderTarget("gemini", _model())
    targets = [primary]
    for target in get_generation_targets("complex"):
        if target not in targets:
            targets.append(target)
    return targets


def _prompt(course_title: str, question: str, retrieval: RetrievalResult) -> str:
    context = "\n\n---\n\n".join(retrieval.note_context)
    return (
        f"Ders: {course_title}\n\n"
        "DERS NOTU KANITLARI:\n" + context + "\n\n"
        "KANIT KURALI:\n"
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

    # One primary call and at most one fallback. A fallback is only safe before
    # the first byte reaches the client; providers are never mixed mid-answer.
    for target in candidates:
        if attempted_api_calls >= 2:
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
            for chunk in provider.generate_stream(
                model=target.model,
                system_prompt=STUDY_SYSTEM_PROMPT,
                history=history[-8:],
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
