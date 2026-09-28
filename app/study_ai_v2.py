"""Gemini-only, source-grounded final generation for Academic AI V2."""
from __future__ import annotations

import os
from typing import Iterator

from app.study_ai import STUDY_SYSTEM_PROMPT, StudyAIError
from app.study_provider import StudyProviderError, get_provider
from app.study_retrieval_v2 import RetrievalResult


def _model() -> str:
    # V2 intentionally has no hidden fallback chain. Changing the model is an
    # explicit release/config decision, never a per-request router decision.
    return (os.getenv("STUDY_V2_GEMINI_MODEL") or "gemini-3.8-flash").strip()


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
    provider = get_provider("gemini")
    try:
        yield from provider.generate_stream(
            model=_model(),
            system_prompt=STUDY_SYSTEM_PROMPT,
            history=history[-8:],
            prompt=_prompt(course_title, question, retrieval),
            attachments=retrieval.attachments,
            temperature=0.22,
            max_output_tokens=7000,
        )
    except StudyProviderError as exc:
        raise StudyAIError(str(exc), code=exc.code, retryable=exc.retryable) from exc


def ask_rag_v2(
    course_title: str,
    question: str,
    history: list[dict],
    retrieval: RetrievalResult,
) -> str:
    return "".join(stream_rag_v2(course_title, question, history, retrieval)).strip()
