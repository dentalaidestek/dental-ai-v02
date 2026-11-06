"""Narrow question consistency checks, never medication status or clinical rules."""
import re

_DENIAL = re.compile(
    r'\bdüzenli\s+(?:bir\s+)?(?:ilacım(?:\s+ve\s+bildiğim\s+alerjim)?\s+yok\b'
    r'|ilaç\s+kullanmıyorum\b)', re.IGNORECASE)
_DETAIL = re.compile(r'\b(?:adı|adları|ismi|isim\w*|doz\w*)\b', re.IGNORECASE)
_REGULAR_SCOPE = re.compile(r'\bdüzenli\b', re.IGNORECASE)
_OTHER_SCOPE = re.compile(r'\b(?:ara sıra|gerektiğinde|hafta\w*|ayda|aylık|iğne\w*|enjeksiyon\w*|daha önce|geçmiş\w*|plan\w*|yeni|reçete edilen|reçetelen\w*|başlan\w*|başlay\w*|öner\w*)\b', re.IGNORECASE)


def denied_regular_medication_question(evidence, quote, question):
    """Reject name/dose requests anchored entirely in an explicit regular-use denial.

    Both question and denial must explicitly concern regular use. Other scopes
    and ambiguous repeated anchors stay reviewable. This
    deliberately does not attempt general Turkish negation or alter patient facts.
    """
    if (not quote.strip() or not _DETAIL.search(question)
            or not _REGULAR_SCOPE.search(question) or _OTHER_SCOPE.search(question)):
        return False
    spans = []
    for match in _DENIAL.finditer(evidence):
        prefix = evidence[evidence.rfind('\n', 0, match.start()) + 1:match.start()]
        if re.match(r'\s*(Geçmiş|Önceden|Belirsiz|Planlanan)\s*:', prefix, re.IGNORECASE):
            continue
        spans.append(match.span())
    # Punctuation is part of the anchor but does not change the denial's scope.
    quote = quote.strip().rstrip('.!?…;,:').rstrip()
    if not quote:
        return False
    occurrences = list(re.finditer(re.escape(quote), evidence))
    return bool(occurrences) and all(any(start <= m.start() and m.end() <= end
                                        for start, end in spans) for m in occurrences)
