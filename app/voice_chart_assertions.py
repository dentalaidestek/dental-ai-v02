"""Affirmative quotation checks before offering existing chart-state candidates.

Not a diagnosis, general-language parser, ASR or speaker classifier. Ambiguous
shorthand can be withheld for manual review. No treatment/drug rules here.
"""
import re

_TERMS = {
    'CARIES': r'\b(?:çürük|karies|caries)\w*',
    'FILLING': r'\b(?:dolgu|restorasyon)\w*',
    'CROWN': r'\b(?:kuron|kron|kaplama)\w*',
    'ROOT_CANAL': r'\bkanal\s+tedavi\w*',
    'EXTRACTED': r'\bçek(?:im|il|ece|elim|ti|ildi)\w*',
    'IMPLANT': r'\bimplant\w*',
}
_UNCERTAIN = (r'\?|\b(?:m[ıiuü](?:d[ıiuü]r)?|olabilir|olmalı|şüphe\w*|galiba|sanırım|bilmiyorum)\b')
_NEGATIVE_VERB = r'\b(?:çekilmedi|yapılmadı|yerleştirilmedi|takılmadı|tamamlanmadı)\b'
_EXISTING = r'\b(?:var|mevcut|yapıldı|yapılmış|tamamlandı|tamamlanmış|çekildi|çekilmiş|yerleştirildi|yerleştirilmiş|takıldı|takılmış|saptandı|görüldü)\b'
_AFFIRMED = {
    'FILLING': r'\bdolgulu\b', 'CROWN': r'\b(?:kuronlu|kronlu|kaplamalı)\b',
    'ROOT_CANAL': r'\bkanal\s+tedavili\b', 'EXTRACTED': r'\bçekil(?:di|miş)\w*|\bçekim\w*\s+(?:yapıl|tamamlan)(?:dı|mış)\w*',
    'IMPLANT': r'\bimplantlı\b', 'OTHER': r'\bkırık\b',
}
_FDI = r'(?<!\d)(?:[1-4][1-8]|[5-8][1-5])(?!\d)'
_TENS = {1:'on',2:'yirmi',3:'otuz',4:'kırk',5:'elli',6:'altmış',7:'yetmiş',8:'seksen'}
_UNITS = {1:'bir',2:'iki',3:'üç',4:'dört',5:'beş',6:'altı',7:'yedi',8:'sekiz'}
_SPOKEN = [(re.compile(r'\b'+_TENS[q]+r'\s+'+_UNITS[n]+r'\b'),f'{q}{n}')
           for q in range(1,9) for n in range(1,9 if q<5 else 6)]


def existing_chart_assertion(status, quote, tooth, spoken_number=''):
    # This analysis copy never replaces the original verbatim quotation.
    text = quote.casefold().replace('\u0307','')
    for pattern, number in _SPOKEN:
        text = pattern.sub(number, text)
    term = _TERMS.get(status)
    if not term and status != 'OTHER':
        return False
    number_pattern = r'(?<!\d)' + re.escape(tooth) + r'(?!\d)'
    ids = set(re.findall(_FDI, text))
    clauses = [m.group() for m in re.finditer(r'[^,;.!?]+[,;.!?]?', text)]
    segments = []
    for clause in clauses:
        segments.extend(re.split(r'(?='+_FDI+r')',clause)
                        if len(set(re.findall(_FDI,clause)))>1 else [clause])
    for clause in segments:
        if term and not re.search(term,clause):
            continue
        if not re.search(number_pattern,clause) and (ids!={tooth} or re.search(_FDI,clause)):
            continue
        if re.search(_UNCERTAIN,clause) or re.search(_NEGATIVE_VERB,clause):
            continue
        if term and re.search(term+r'\s+(?:\w+\s+)?(?:yok\w*|değil\w*)\b',clause):
            continue
        affirmed = bool(status in _AFFIRMED and re.search(_AFFIRMED[status],clause))
        # EXTRACTED specifically needs a completed extraction assertion. Other
        # statuses need a predicate attached to that status, not another procedure.
        if status != 'EXTRACTED' and term:
            affirmed |= bool(re.search(term+r'\s+(?:(?:zaten|halen)\s+)?'+_EXISTING,clause))
        if status == 'OTHER':
            affirmed |= bool(re.search(_EXISTING,clause))
        if affirmed:
            return True
    return False
