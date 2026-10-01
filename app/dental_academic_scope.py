"""Zero-provider scope routing for Dental Academic questions."""
from __future__ import annotations

import re

from app.dental_semantics import analyze_dental_text

# Deliberately high-precision blocks. Unknown questions are allowed to reach
# retrieval so legitimate biomedical/dental terminology is not rejected.
_CLEAR_NON_DENTAL = {
    "matematik", "geometri", "programlama", "yazılım", "yazilim", "algoritma",
    "muhasebe", "finans", "iktisat", "ekonomi", "pazarlama",
    "anayasa", "medeni hukuk", "ceza hukuku", "edebiyat", "coğrafya", "cografya",
    "otomotiv", "mimarlık", "mimarlik", "inşaat", "insaat",
}
_STUDY_ACTIONS = {
    "özetle", "ozetle", "anlat", "açıkla", "acikla", "karşılaştır", "karsilastir",
    "soru hazırla", "soru hazirla", "quiz", "sınav", "sinav", "önemli yerler",
    "onemli yerler", "devam", "tekrar anlat", "bunu açıkla", "bunu acikla",
}
_FOLLOWUP = re.compile(
    r"^(peki|tamam|devam|neden|nasıl|nasil|hangisi|bunu|onu|burayı|burayi|"
    r"biraz daha|detaylandır|detaylandir|örnek ver|ornek ver)\b",
    re.IGNORECASE,
)


def classify_academic_question_scope(
    query: str, *, recent_history: list[dict] | None = None
) -> str:
    """Return DENTAL, STUDY_ACTION, FOLLOWUP, NON_DENTAL or UNKNOWN.

    UNKNOWN is intentionally not rejected. Retrieval evidence is the second
    gate, which protects uncommon dental/biomedical terminology without an AI
    classifier call.
    """
    text = " ".join((query or "").casefold().split())
    if not text:
        return "UNKNOWN"

    features = analyze_dental_text(text)
    if features.node_ids or features.specialties or features.tooth_numbers or features.imaging_types:
        return "DENTAL"

    # Conversational referents take precedence over generic study verbs:
    # "bunu biraz daha açıkla" depends on the preceding turn, while a standalone
    # "bu notu açıkla" remains a study action.
    if _FOLLOWUP.search(text) and recent_history:
        return "FOLLOWUP"

    if any(term in text for term in _STUDY_ACTIONS):
        # Explicit study commands belong to the current course unless they also
        # contain a clearly unrelated subject.
        if not any(term in text for term in _CLEAR_NON_DENTAL):
            return "STUDY_ACTION"

    if any(term in text for term in _CLEAR_NON_DENTAL):
        return "NON_DENTAL"
    return "UNKNOWN"


def should_block_academic_question(
    query: str, *, recent_history: list[dict] | None = None
) -> bool:
    return classify_academic_question_scope(query, recent_history=recent_history) == "NON_DENTAL"
