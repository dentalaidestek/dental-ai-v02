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
ACKNOWLEDGEMENT_RESPONSE = 'Rica ederim. Hazır olduğunda devam edebiliriz.'


def conversational_acknowledgement(query: str) -> bool:
    text = ' '.join((query or '').translate(_FOLD).lower().split())
    return bool(re.fullmatch(r'(?:tamam|tesekkurler|tesekkur ederim|sag\s*ol|eyvallah|anladim)[.! ]*', text))


def _latest_assistant(history: list[dict] | None) -> dict | None:
    # A deterministic courtesy exchange does not replace a pending question.
    from app.academic_request_slots import REPAIR_RESPONSE
    return next((item for item in reversed((history or [])[-8:])
                 if str(item.get('role') or '').casefold() in {'assistant', 'ai'}
                 and str(item.get('content') or '').strip() not in {ACKNOWLEDGEMENT_RESPONSE, REPAIR_RESPONSE}), None)


def _latest_study_user(history: list[dict] | None) -> dict | None:
    from app.academic_request_slots import conversational_repair
    return next((item for item in reversed((history or [])[-8:])
                 if str(item.get('role') or '').casefold() in {'user', 'human'}
                 and not conversational_acknowledgement(str(item.get('content') or ''))
                 and not conversational_repair(str(item.get('content') or ''))), None)


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


def _free_answer_intent(query: str) -> bool:
    """A short declarative response can answer a pending actual question.

    New requests and conversation controls retain their own intent. This does
    not classify a response as factually correct; generation must grade it
    against the selected question and retrieved note evidence.
    """
    from app.academic_task_language import parse_study_operation, elliptical_study_request
    text = ' '.join((query or '').translate(_FOLD).lower().split())
    if not text or len(text) > 600 or '?' in text:
        return False
    from app.academic_request_slots import conversational_repair
    if conversational_repair(query):
        return False
    if elliptical_study_request(query):
        return False
    if re.fullmatch(r'(?:tamam|tesekkurler|tesekkur ederim|sag ol)[.! ]*', text):
        return False
    operation = parse_study_operation(query)
    if operation and operation.task:
        return False
    return not re.search(
        r'\b(?:nedir|nasil|neden|niye|hangi|kac|ne|devam|baska|yeni|degistir|'
        r'birak|bosver|onceki|sonraki|konu|konuyu|don|gec|gecelim|bakalim|ogret|ozetle|hazirla|anlat|acikla|'
        r'tablo|format|ayni|anlamadim|tekrar)\b|\bdaha\s+(?:basit|detayli|kisa)\b', text)


def evidence_followup(*, resolved_query: str, retrieval_mode: str,
                      has_evidence: bool, missing_facets: tuple[str, ...] = ()) -> str:
    """Keep insufficient retrieval conversational without inventing an answer.

    Coverage failures are system/source failures, not missing user topics.
    An explicit topic is acknowledged separately from an unresolved referent.
    This changes no evidence gate and makes no provider call.
    """
    from app.dental_query_intent import build_dental_requirement_plan
    if retrieval_mode == 'coverage':
        return ('Dersin tamamından çalışmak istediğini anladım. Ancak notların tümünden '
                'güvenilir içerik hazırlayamadım. İstersen belirli bir konuyla başlayabiliriz; '
                'hangi konuyu çalışmak istersin?')
    plan = build_dental_requirement_plan(resolved_query)
    subjects = ' ve '.join(plan.subject_terms[:3])
    if subjects:
        if has_evidence and missing_facets:
            missing = ', '.join(missing_facets)
            return (f'{subjects} hakkında notlarda içerik buldum; ancak {missing} için '
                    'yeterli kaynak bulamadım. Bu başlığın notlarda geçen diğer adını '
                    'veya ilgili slayttan kısa bir ifadeyi paylaşır mısın?')
        return (f'{subjects} konusunu çalışmak istediğini anladım. Bu isteği yanıtlayacak '
                'yeterli not içeriğini henüz eşleştiremedim. Notlarda geçen diğer adını '
                'veya ilgili slayttan kısa bir ifadeyi paylaşır mısın?')
    return ('Notlardan çalışmana yardımcı olabilirim. Hangi konuyu kastettiğini '
            'netleştirelim: bir konu adı yazabilir veya dersin tamamını çalışmamı isteyebilirsin.')


def active_question_reference(query: str, history: list[dict] | None) -> QuestionReference | None:
    """Bind short answers only to a single actual question, never guess a batch item."""
    folded = ' '.join((query or '').translate(_FOLD).lower().split())
    from app.academic_task_language import parse_study_operation
    operation = parse_study_operation(query)
    if operation and operation.generate:
        # A wait-for-my-answer instruction controls a NEW quiz; it is not
        # a reference to the old question just because it says "cevabımı".
        return None
    answer = bool(_ANSWER.fullmatch(folded))
    reference = bool(re.search(
        r'\b(?:bu|onceki|bir onceki|son|az onceki)\s+soru\w*\b|'
        r'\b(?:cevabimi|cevabim|yanitim|yanitimi)\b', folded,
    ))
    if not (answer or reference or _free_answer_intent(query)):
        return None
    latest = _latest_assistant(history)
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
    if not (answer or reference or _OPTIONS.search(text)):
        # A rhetorical question inside a lecture is not a pending quiz. Free
        # answers require an actual question-generation turn or quiz options.
        from app.academic_task_language import parse_study_operation
        latest_user = _latest_study_user(history)
        operation = parse_study_operation(str(latest_user.get('content') or '')) if latest_user else None
        if not operation or not operation.generate:
            return None
    return QuestionReference(text[:4000], stem, number)


def answer_needs_reference(query: str, history: list[dict] | None) -> bool:
    folded = ' '.join((query or '').translate(_FOLD).lower().split())
    if _ANSWER.fullmatch(folded):
        return active_question_reference(query, history) is None
    if not _free_answer_intent(query):
        return False
    latest = _latest_assistant(history)
    if not latest:
        return False
    body = str(latest.get('content') or '')[:16000]
    if len(numbered_items(body)) <= 1:
        return False
    if _OPTIONS.search(body) or re.search(r'(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?soru\s+\d+', body):
        return True
    from app.academic_task_language import parse_study_operation
    latest_user = _latest_study_user(history)
    operation = parse_study_operation(str(latest_user.get('content') or '')) if latest_user else None
    return bool(operation and operation.generate)


def numbered_answer_references(query: str, history: list[dict] | None) -> list[QuestionReference]:
    """Bind '1A, 2C' to the current real question batch, keeping every answer."""
    text = (query or '').translate(_FOLD).lower()
    assignment = re.compile(r'\b(?:soru\s*)?(\d{1,3})\s*[.):=\-]?\s*([a-e])\b')
    answers = list(assignment.finditer(text))
    remainder = assignment.sub(' ', text)
    remainder = re.sub(r'\b(?:cevaplarim|cevabim|yanitlarim|yanitim|bence|ve)\b', ' ', remainder)
    if not answers or re.search(r'\w', remainder):
        return []
    latest = _latest_assistant(history)
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
    from app.academic_task_language import parse_study_operation
    operation = parse_study_operation(query)
    learner_practice = bool(operation and operation.generate
                            and re.search(r'\b(?:beni|bizi|kendimi)\b', folded)
                            and re.search(r'\b(?:calistir|sina)\w*\b', folded))
    if (re.search(r'\b(?:cevabimi|yanitimi|cevaplarimi|yanitlarimi)\s+bekle\b', folded)
            or re.search(r'\b(?:tek tek|birer birer|sirayla)\b.*\bsoru\w*\b', folded)
            or learner_practice):
        return (
            'Etkileşimli çalışma: bu turda yalnız bir soru sor ve öğrencinin '
            'cevabını bekle. Cevabı/anahtarı henüz açıklama. İstenen toplam soru '
            'sayısı bütün çalışmaya aittir; hepsini bu turda dökme. '
            'Sonraki turda önce öğrencinin yanıtını not kanıtıyla değerlendir.'
        )
    return ''
