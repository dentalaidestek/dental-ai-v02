"""Resolve user-selected question references from actual bounded chat history."""
from __future__ import annotations

import re
from dataclasses import dataclass

_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
_ITEM = re.compile(
    r'(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:soru\s+)?'
    r'(\d{1,3})(?:[.)\:]|\s*(?:\*\*)?\s*$)\s*(?:\*\*)?\s*'
)
_OPTIONS = re.compile(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?[A-E][.)\:]\s*')
_ANSWER = re.compile(r'(?:cevabim\s*[:=]?\s*|bence\s+|cevap\s*[:=]?\s*)?[a-e](?:\s+sikki)?[.!]?')


def numbered_items(body: str) -> list[tuple[int, str]]:
    """Support both numbered lists and the system prompt's 'Soru N' format."""
    matches = list(_ITEM.finditer(body or ''))
    return [(int(item.group(1)), (body[item.end():matches[i + 1].start()]
            if i + 1 < len(matches) else body[item.end():]).strip())
            for i, item in enumerate(matches)]


def question_topic(body: str) -> str:
    # Options are distractors, never independently owned retrieval subjects.
    stem = _OPTIONS.split(body or '', maxsplit=1)[0]
    return ' '.join(stem.split())[:700]


@dataclass(frozen=True)
class QuestionReference:
    text: str
    topic: str
    number: int | None = None


def active_question_reference(query: str, history: list[dict] | None) -> QuestionReference | None:
    """Bind short answers only to a single actual question, never guess a batch item."""
    folded = ' '.join((query or '').translate(_FOLD).lower().split())
    answer = bool(_ANSWER.fullmatch(folded))
    reference = bool(re.search(
        r'\b(?:bu|onceki|bir onceki|son|az onceki)\s+soru\w*\b|'
        r'\b(?:cevabimi|cevabim|yanitim|yanitimi)\b', folded,
    ))
    if not (answer or reference):
        return None
    latest = next((item for item in reversed((history or [])[-8:])
                   if str(item.get('role') or '').casefold() in {'assistant', 'ai'}), None)
    if latest is None:
        return None
    body = str(latest.get('content') or '')[:16000]
    items = numbered_items(body)
    if len(items) > 1:
        return None
    if items:
        number, text = items[0]
    else:
        number, text = None, body
    stem = question_topic(text)
    if not stem or ('?' not in stem and not _OPTIONS.search(text)):
        return None
    return QuestionReference(text[:4000], stem, number)


def answer_needs_reference(query: str, history: list[dict] | None) -> bool:
    folded = ' '.join((query or '').translate(_FOLD).lower().split())
    return bool(_ANSWER.fullmatch(folded)) and active_question_reference(query, history) is None


def numbered_answer_references(query: str, history: list[dict] | None) -> list[QuestionReference]:
    """Bind '1A, 2C' to the current real question batch, keeping every answer."""
    text = (query or '').translate(_FOLD).lower()
    assignment = re.compile(r'\b(?:soru\s*)?(\d{1,3})\s*[.):=\-]?\s*([a-e])\b')
    answers = list(assignment.finditer(text))
    remainder = assignment.sub(' ', text)
    remainder = re.sub(r'\b(?:cevaplarim|cevabim|yanitlarim|yanitim|bence|ve)\b', ' ', remainder)
    if not answers or re.search(r'\w', remainder):
        return []
    latest = next((item for item in reversed((history or [])[-8:])
                   if str(item.get('role') or '').casefold() in {'assistant', 'ai'}), None)
    if latest is None:
        return []
    items = dict(numbered_items(str(latest.get('content') or '')[:16000]))
    numbers = list(dict.fromkeys(int(answer.group(1)) for answer in answers))
    if any(number not in items for number in numbers):
        return []
    return [QuestionReference(items[number][:4000], question_topic(items[number]), number)
            for number in numbers]


def dialogue_rules(query: str, history: list[dict] | None) -> str:
    """Make the requested study interaction explicit without another AI call."""
    reference = active_question_reference(query, history)
    references = numbered_answer_references(query, history) or ([reference] if reference else [])
    if references:
        return (
            'Öğrenci yeni bir konu sormuyor; aşağıdaki gerçek sohbet sorusuna cevap '
            'veriyor veya onu açıklamanı istiyor. Cevabını yalnız getirilen ders '
            'kanıtlarıyla değerlendir; doğru seçeneği önceki model cevabından varsayma. '
            'Kendiliğinden yeni soru seti üretme.\n'
            'ÖĞRENCİNİN REFERANS VERDİĞİ SORULAR:\n'
            + '\n\n'.join((f'Soru {item.number}:\n' if item.number else '') + item.text
                           for item in references)
        )
    folded = ' '.join((query or '').translate(_FOLD).lower().split())
    if (re.search(r'\b(?:cevabimi|yanitimi|cevaplarimi|yanitlarimi)\s+bekle\b', folded)
            or re.search(r'\b(?:tek tek|birer birer|sirayla)\b.*\bsoru\w*\b', folded)):
        return (
            'Etkileşimli çalışma: bu turda yalnız bir soru sor ve öğrencinin '
            'cevabını bekle. Cevabı/anahtarı henüz açıklama. İstenen toplam soru '
            'sayısı bütün çalışmaya aittir; hepsini bu turda dökme. '
            'Sonraki turda önce öğrencinin yanıtını not kanıtıyla değerlendir.'
        )
    return ''
