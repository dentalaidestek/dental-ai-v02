"""Clause-scoped study operations, separate from dental subjects and evidence.

This layer reads requested transformations. It does not recognize dental entities,
repair their names, infer missing subjects, or validate factual answers.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import re

_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
STUDY_NUMBER_WORDS = dict(zip('bir iki uc dort bes alti yedi sekiz dokuz on yirmi otuz kirk elli altmis yetmis seksen doksan yuz'.split(),
                            (1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100)))
_STUDY_COUNT_WORDS = frozenset(STUDY_NUMBER_WORDS)
STUDY_COUNT_PATTERN = (r'(?:\d{1,3}|(?:on|yirmi|otuz|kirk|elli|altmis|yetmis|seksen|doksan)'
                       r'(?:\s+(?:bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz))?'
                       r'|(?:bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|yuz))')


def study_count_value(value: str) -> int:
    folded = value.translate(_FOLD).lower().strip()
    return int(folded) if folded.isdigit() else sum(STUDY_NUMBER_WORDS[word] for word in folded.split())


def comprehension_followup(query: str) -> bool:
    """An omitted object in a comprehension repair requires prior context."""
    text = ' '.join(strip_request_prefix(query).translate(_FOLD).lower().split())
    return bool(re.fullmatch(r'(?:anlamadim|anlayamadim|kafam\s+karisti)'
        r'(?:\s+(?:biraz\s+)?(?:daha\s+)?(?:basit|sade|anlasilir|detayli)'
        r'(?:\s+bir\s+dille)?\s+(?:anlat|acikla)(?:sana|sene)?)?[.!? ]*', text))


def elliptical_study_request(query: str) -> str | None:
    """Closed grammatical clauses with an omitted subject, never noun fuzzing."""
    text = ' '.join(strip_request_prefix(query).translate(_FOLD).lower().split()).strip(' .!?')
    if re.fullmatch(r'(?:bir\s+|ondan\s+bir\s+)?onceki\s+(?:konuya|basliga)\s+don'
                    r'(?:[,;]\s+(?:daha\s+)?(?:basit|sade|detayli|ayrintili)\s+(?:anlat|acikla))?', text):
        return 'explain'
    from app.academic_request_slots import output_slots
    slots = output_slots(query)
    if slots:
        return slots.kind
    priority = study_priority_request(query)
    if priority:
        return priority
    if comprehension_followup(query):
        return 'explain'
    # Dissatisfaction/outline completion modifies the existing study output.
    # Full clauses protect explicit clinical nouns from being erased.
    feedback = r'(?:(?:bu|bu\s+anlattigin|anlattiklarin|yanitin|cevabin)\s+)?(?:cok\s+)?(?:yuzeysel|kisa|eksik|yetersiz)'
    clauses = [clause.strip() for clause in re.split(r'[.!?;,]+', text) if clause.strip()]
    if len(clauses) > 1 and all(re.fullmatch(feedback, clause) for clause in clauses[:-1]):
        text = clauses[-1]
    outline = r'(?:her|tum|butun|diger|kalan)\s+(?:baslik|basligi|basliklari|basliklar|konu|konuyu|konulari|konular)'
    text = re.sub(r'^(?:bu\s+)?(?:cok\s+)?(?:yuzeysel|kisa|eksik|yetersiz)[,;:]?\s+', '', text)
    predicate = (r'(?:acikla|anlat|detaylandir)' + _REQUEST_END
                 + r'(?:\s+(?:misin|misiniz))?'
                 + r'|(?:acikla|anlat|detaylandir)(?:r|ir|ar|er)\s+(?:misin|misiniz)'
                 + r'|nerede|neredeler|goremedim')
    if re.fullmatch(outline + r'\s+(?:(?:da|de|tek\s+tek|ayri\s+ayri)\s+)?(?:' + predicate + ')', text):
        return 'outline'
    if re.fullmatch(r'(?:biraz\s+)?(?:daha\s+)?(?:detayli|ayrintili|derinlemesine|basit|sade|anlasilir)'
                    r'\s+(?:' + predicate + ')', text):
        return 'explain'
    if re.fullmatch(feedback, text):
        return 'explain'
    if re.fullmatch(r'(?:bu\s+)?(?:cok\s+)?(?:yuzeysel|kisa|eksik|yetersiz)', text):
        return 'explain'
    if re.fullmatch(r'(?:bir\s+)?ornek\s+(?:ver|versene|verir\s+misin|goster)', text):
        return 'explain'
    if re.fullmatch(r'nasil\s+(?:uygulanir|uygulaniyor|uygulayacagiz|yapilir|yapiliyor)', text):
        return 'procedure'
    if re.fullmatch(r'(?:neden|niye)\s+(?:boyle|bu\s+sekilde)\s+(?:olur|oluyor|yapilir|yapiliyor)', text):
        return 'cause'
    if re.fullmatch(r'(?:dozu|dozunu|miktari|miktarini)\s+(?:da\s+)?(?:soyle|ver|belirt|acikla)', text):
        return 'value'
    if re.fullmatch(r'(?:bir|\d{1,2})\s+(?:tane\s+)?daha\s+sor(?:sana|sene)?', text):
        return 'generate_questions'
    return None


def study_priority_request(query: str) -> str | None:
    """Subject-omitted exam selection versus verifiable source emphasis.

    Full clause matching leaves named and unknown clinical subjects intact.
    Feedback rejects a prior selection; it never supplies a new medical noun.
    """
    text = ' '.join(strip_request_prefix(query).translate(_FOLD).lower().split()).strip(' .!?')
    text = re.sub(r'^(?:bence\s+)?(?:buradan|burdan|bundan|bunlardan)\s+'
                  r'(?:gelmez|cikmaz|sorulmaz)[,;.!? ]+','', text)
    text = ' '.join(remove_source_reference(text).split()).strip(' .!?')
    examiner = r'(?:hoca|hocanin|hocamiz|hocamizin|ogretmen|ogretmenin)'
    if re.fullmatch(r'(?:' + examiner + r'\s+)?(?:nereden|nerden|ne|neler|nasil|hangi\s+konulardan)'
                   r'\s+(?:sorabilir|sorar|soracak)', text):
        return 'exam_points'
    selection = (r'(?:en\s+)?(?:kritik|onemli|oncelikli)\s+(?:yerleri|noktalari|konulari|basliklari)'
                 r'\s+(?:ayir|sec|belirle|bul|listele|goster|cikar)')
    if re.fullmatch(selection, text):
        return 'exam_points'
    if re.fullmatch(r'(?:' + examiner + r'\s+)?(?:nereden|nerden|nasil|ne)\s+'
                   r'sorabilecegini\s+(?:anlat|acikla|goster)', text):
        return 'exam_points'
    if re.fullmatch(r'(?:buradan|burdan|bundan)\s+nasil\s+soru\s+(?:cikar|sorulur)'
                   r'|neye\s+(?:daha\s+)?(?:cok\s+)?calisayim', text):
        return 'exam_points'
    if re.fullmatch(r'(?:sinavda\s+)?(?:nereden|nerden|ne|neler)\s+'
                   r'(?:cikabilir|cikar|sorulabilir|sorulur)', text):
        return 'exam_points'
    emphasis = (r'(?:(?:' + examiner + r')\s+)?(?:ozellikle\s+)?'
                r'(?:(?:vurguladigi|isaretledigi|altini\s+cizdigi|uzerinde\s+durdugu)\s+)?'
                r'(?:(?:isaretli|vurgulu|vurgulanan|isaretlenmis|altı\s+cizili|alti\s+cizili)\s+)?'
                r'(?:yerler|yerleri|noktalar|noktalari|kisimlar|kisimlari|bolumler|bolumleri)')
    if (re.search(r'\b(?:vurguladigi|isaretledigi|cizdigi|durdugu|isaretli|vurgulu|vurgulanan|isaretlenmis|cizili)\b', text)
            and re.fullmatch(emphasis + r'\s+(?:var\s+mi|nerede|nereler|hangileri|'
                             r'goster|bul|listele|gosterir\s+misin)', text)):
        return 'source_emphasis'
    # Locate actual annotations/typography, not clinical color findings or
    # an arbitrary noun phrase containing "important".
    appearance = (r'(?:kirmiziyla|maviyle|sariyla)\s+yazilan|kalin\s+yazilmis|'
                  r'yildiz\s+konmus|(?:' + examiner + r')\s+onemli\s+dedigi')
    if re.fullmatch(r'(?:' + appearance + r')\s+(?:yerleri|basliklar|kisimlari|noktalari)'
                   r'\s+(?:getir|bul|goster|hangileri|nerede)', text):
        return 'source_emphasis'
    if re.fullmatch(r'hangi\s+sayfalarda\s+(?:' + examiner + r')\s+'
                   r'(?:isaret|yildiz)\s+koymus', text):
        return 'source_emphasis'
    return None


def wants_deeper_evidence(query: str) -> bool:
    """Requested depth changes evidence budget, never relevance thresholds."""
    text = ' '.join((query or '').translate(_FOLD).lower().split())
    if re.search(r'\b(?:detay|ayrinti)\w*\s+(?:istemiyorum|istemiyoruz|olmasin)\b'
                 r'|\b(?:detaylandirma|ayrintilandirma)\b'
                 r'|\b(?:detayli|ayrintili)\s+(?:anlatma|aciklama\s+istemiyorum)\b', text):
        return False
    if elliptical_study_request(query) == 'outline':
        return True
    if elliptical_study_request(query) == 'explain' and re.search(r'\b(?:yuzeysel|eksik|yetersiz)\b', text):
        return True
    if re.fullmatch(r'(?:bu\s+)?(?:cok\s+)?(?:yuzeysel|eksik|yetersiz)[.!? ]*',
                    strip_request_prefix(query).translate(_FOLD).lower()):
        return True
    return bool(re.search(r'\b(?:detaylandir|ayrintilandir)(?:sana|sene)?\b'
                         r'|\b(?:detayli|ayrintili|derinlemesine)\b', text))


def strip_request_prefix(query: str) -> str:
    """Strip bounded discourse prefixes without fuzzy matching medical nouns."""
    clean = (query or '').strip()
    clean = re.sub(r'(?iu)^(?:cevapları|cevaplari|yanıtları|yanitlari|cevap\s+anahtarını|cevap\s+anahtarini)'
                   r'\s+(?:söyleme|soyleme|gösterme|gosterme)[,;:.]?\s+', '', clean)
    clean = re.sub(r'(?iu)^(?:rica\s+etsem|mümkünse|mumkunse)[,;:]?\s+', '', clean)
    for _ in range(3):
        polite = re.match(r'(?iu)^(?:rica\s+etsem|mümkünse|mumkunse)[,;:]?\s+(.+)$', clean)
        if polite:
            clean = polite.group(1).strip()
            continue
        first = re.match(r'^(\S+)[,;:]?\s+(.+)$', clean)
        if first is None:
            break
        token = first.group(1).strip(',;:').translate(_FOLD).lower()
        token = re.sub(r'(.)\1+', r'\1', token)
        if token not in {'ya', 'yok', 'hayir', 'kral', 'hocam', 'abi', 'lutfen', 'bana', 'simdi', 'peki', 'acaba', 'dostum', 'baskan'}:
            break
        clean = first.group(2).strip()
    return clean

_COURSE_SOURCE_RE = re.compile(
    r'\b(?:(?:bu|tum|butun)\s+)?(?:ders\s+)?'
    r'(?:(?:not|slayt|materyal|belge|dosya)(?:lar|ler)?'
    r'(?:u|unu|un|ta|tan|taki|i|yi|ini|larini|lerini|dan|den|indan|inden|inda|inde|inin|ina|'
    r'larindan|lerinden|indaki|indeki|larindaki|lerindeki|daki|deki|da|de|larda|lerde|larin|lerin|larinin|lerinin|lara|lere|imi|imdan)?'
    r'|ders(?:in\s+tamam(?:i|ini|indan)|i|in))\b'
)


def remove_source_reference(query: str) -> str:
    """A note-source adjunct is not part of the requested medical topic."""
    folded = (query or '').translate(_FOLD).lower()
    pattern = re.compile(_COURSE_SOURCE_RE.pattern
                         + r'(?:\s+(?:gore|gecen|bahsedilen|anlatilan|yer\s+alan))?')
    clean = query or ''
    for match in reversed(list(pattern.finditer(folded))):
        # An unqualified material noun after a subject denotes that clinical
        # material (ABC materyali), whereas bu/ders materyali owns source scope.
        if match.group(0).startswith('materyal'):
            prefix = folded[:match.start()].strip(' ,;:.!?')
            if prefix and not re.fullmatch(r'(?:lutfen|bana|simdi|peki)(?:\s+(?:lutfen|bana|simdi|peki))*', prefix):
                continue
        clean = clean[:match.start()] + ' ' + clean[match.end():]
    return clean

def course_source_request(query: str) -> bool:
    """Recognize a course source as the argument of a study operation.

    Task/style words between that source argument and the operation are not
    topical search terms. Unknown nouns remain subjects, so naming a topic
    inside the notes does not silently turn into a whole-course request.
    Entity recognition is deliberately left to the caller.
    """
    operation = parse_study_operation(query)
    if operation is None or operation.task is None or operation.past:
        return False
    text = strip_request_prefix(query).translate(_FOLD).lower()
    text = ' '.join(text.split())
    source = _COURSE_SOURCE_RE.search(text)
    if source is None:
        return False
    prefix = text[:source.start()].strip(' ,.!?')
    if prefix and not re.fullmatch(r'(?:lutfen|bana|simdi|peki)(?:\s+(?:lutfen|bana|simdi|peki))*', prefix):
        return False
    tail = text[source.end():]
    action_roots = r'(?:ozetle|toparla|acikla|anlat|ogret|hazirla|uret|olustur|yaz|yap|cikar|listele|sirala|goster|belirle|sec|ayir|bul|ayikla|getir|donustur|cevir|sor|calisalim|calistir|sina)'
    action = re.search(r'\b' + action_roots + _REQUEST_END
                       + r'|\b' + action_roots + r'(?:r|ir|ar|er)\s+(?:misin|misiniz)\b', tail)
    if action is None:
        return False
    argument = tail[:action.start()]
    # Output/persona/goal modifiers describe how to transform the source.
    # These are shared language rules, independent of any UI preset text.
    argument = re.sub(
        r'\b(?:sinav|final|vize)(?:a|da|dan)?\s+(?:odakli|icin|yonelik)\b'
        r'|\b(?:bir\s+)?(?:hoca|ogretmen|ogrenci)(?:ya|ye)?\s+gibi\b'
        r'|\b(?:mantigini|mantik)\s+kurarak\b'
        r'|\b(?:gerektiginde\s+)?orneklerle\b'
        r'|\b(?:basit|sade|anlasilir)\s+bir\s+dille\b'
        r'|\b(?:calisabilecegim|calisilabilir)\s+(?:bir\s+)?hale\b'
        r'|\b(?:bastan\s+sona|madde\s+madde|tek\s+tek|adim\s+adim)\b'
        r'|\b(?:coktan\s+secmeli|acik\s+uclu|dogru\s+yanlis)\b',
        ' ', argument,
    )
    tokens = re.findall(r'\w+', argument)
    modifiers = {
        'konu', 'konuyu', 'konulari', 'konularini', 'icerigi', 'icerigini',
        'bana', 'beni', 'benim', 'icin', 've', 'bir', 'sekilde', 'olarak', 'tum', 'butun',
        'kisa', 'kisaca', 'detayli', 'ayrintili', 'basit', 'sade', 'anlasilir',
        'yuksek', 'verimli', 'zor', 'zorlayici', 'kolay', 'orta',
        'soru', 'sorular', 'sorulari', 'test', 'tane', 'adet',
        'kritik', 'onemli', 'yerleri', 'yerlerini', 'noktalar', 'noktalari', 'noktalarini',
        'baslik', 'basliklari', 'basliklarini',
        'calisma', 'plani', 'planini', 'programi', 'programini', 'mantigiyla', 'her', 'tek',
        'sinava', 'finale', 'vizeye',
        'tamami', 'tamamini', 'ozetini', 'okuyup',
        'hepsini', 'kullanarak', 'ana', 'atlamadan', 'ayrintilariyla',
    }
    return all(token in modifiers or token in _STUDY_COUNT_WORDS or token.isdigit() for token in tokens)


def subjectless_study_request(query: str) -> bool:
    """Study controls alone request work on the active topic/course, not FTS words."""
    operation = parse_study_operation(query)
    if operation is None or operation.task is None or operation.past:
        return False
    text = strip_request_prefix(query).translate(_FOLD).lower()
    text = re.sub(r'\b(' + '|'.join(_ACTION_ROOTS | {'sor'})
                  + r')(?:r|ir|ar|er)\s+(?:misin|misiniz)\b', r'\1', text)
    # Remove complete control constructions rather than dental noun stems.
    text = re.sub(r'\b(?:cevabimi|yanitimi|cevaplarimi|yanitlarimi)\s+bekle\b', ' ', text)
    text = re.sub(r'\b(?:coktan secmeli|acik uclu|dogru yanlis|tek tek|birer birer)\b', ' ', text)
    text = re.sub(r'\b(?:sinav|final|vize)\s+(?:icin|odakli|yonelik)\b', ' ', text)
    text = re.sub(r'\b(?:calisabilecegim|calisilabilir)\s+(?:bir\s+)?hale\s+(?:getir|cevir|donustur)\b', 'ozetle', text)
    controls = {
        'bana', 'beni', 'lutfen', 'bir', 'tane', 'adet', 've', 'icin',
        'soru', 'sorular', 'test', 'quiz', 'alistirma', 'deneme',
        'kolay', 'orta', 'zor', 'zorlayici', 'farkli', 'yeni',
        'ozet', 'kisa', 'kisaca', 'detayli', 'ayrintili', 'basit',
        'calisma', 'plani', 'planini', 'programi', 'programini', 'sinava', 'finale', 'vizeye', 'simdi', 'sonra', 'bekle', 'olsun', 'istiyorum', 'lazim',
    }
    return all(token in controls or token in _STUDY_COUNT_WORDS or token.isdigit()
               or re.fullmatch(r'(?:ozetle|toparla|acikla|anlat|ogret|sor|hazirla|uret|olustur|yaz|cikar|yap|sina|calistir)' + _REQUEST_END, token)
               for token in re.findall(r'\w+', text))
# Orthographic rescue is limited to grammar/operators, with unique one-edit
# targets. Productive nominal inflections preserve the operation's argument.
_ACTION_ROOTS = frozenset(('acikla anlat ogret ozetle toparla birlestir yogunlastir sikistir '
    'uret hazirla olustur yaz cikar listele ayir grupla goster belirt bul belirle '
    'coz eslestir bagla degerlendir kontrol incele kur cevir yap sec ayikla dogrula donustur').split())
_REQUEST_SUFFIXES = ('', 'yin','in','sana','sene','mani','manizi','man','mam','r','ir',
    'yabilir','abilir','mek','mak','ip','yip')
_SOURCE_ROOTS = ('cikmis','gecmis')
_NEGATIVE_FORMS = frozenset(('ozetleme uretme hazirlama olusturma cozme anlatma '
    'ogretme eslestirme baglama listeleme ayirma gosterme bulma').split())
_NOUN_ROOTS = ('secenek','sik','oncul','karsilik','konu','baslik','soru','sinav','sozlu',
    'benzer','benzeyen','dagilim','tekrar','surekli','calisma','mutlaka','ozet')
_NOUN_SUFFIXES = ('','lar','lari','larini','larinin','larin','larda','lardan','larla',
    'lara','lere','ler','leri','lerini','lerine','lerinin','lerin','lerde','lerden','lerle','le','la',
    'i','ini','inin','u','unu','unun','a','e','ya','ye','yi','yu','na','ne','nu','ni',
    'nin','nun','ta','te','tan','ten','da','de','dan','den','si','sini','sinin','su','sunu','suna','sunun','ki')
def _noun_forms(root: str) -> frozenset[str]:
    # Buffer consonants depend on the stem ending. A Cartesian product
    # invents forms such as soru+unu and ozet+ni, creating false ambiguity
    # against real inflections during one-edit rescue.
    vowel = root[-1] in 'aeiou'
    invalid = ({'i','ini','inin','u','unu','unun','a','e'} if vowel else
               {'yi','yu','ya','ye','na','ne','nu','ni','nin','nun'})
    return frozenset(root + suffix for suffix in _NOUN_SUFFIXES if suffix not in invalid)


_DOMAINS = {
    'relationship': frozenset(('dayandigi','bagli','yoklanan','gecen','hareketle')),
    'action': frozenset(b+s for b in _ACTION_ROOTS for s in _REQUEST_SUFFIXES),
    'source': frozenset().union(*(_noun_forms(b) for b in _SOURCE_ROOTS)),
    'question': _noun_forms('soru'),
    'option': frozenset().union(*(_noun_forms(b) for b in ('sik','secenek','oncul'))),
    'argument': frozenset().union(*(_noun_forms(b) for b in _NOUN_ROOTS)) | frozenset((
        'karsiligi','karsiligini','karsiligina','karsiliklari','siklarini','siklarinin',
        'siklarin','siklarina','siklarindan','mantigini','mantigi','mantiginin',
        'baglantisini','baglantiyi','baglantilari','baglantilarini','dogru','cevabina',
        'cevabi','cevabin','cevabini','cevabinin','dogrulugunu','anlatir',
        'basligi','basligini','basligina','basliginin')),
}

def _one_edit(a: str,b: str) -> bool:
    if abs(len(a)-len(b))>1:return False
    if len(a)==len(b):
        ds=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        return len(ds)==1 or (len(ds)==2 and ds[1]==ds[0]+1 and a[ds[0]]==b[ds[1]] and a[ds[1]]==b[ds[0]])
    short,long=(a,b) if len(a)<len(b) else (b,a)
    i=0
    while i<len(short) and short[i]==long[i]:i+=1
    return short[i:]==long[i+1:]

_INDEX = {domain:{n:tuple(x for x in forms if len(x)==n) for n in range(3,30)}
          for domain,forms in _DOMAINS.items()}
@lru_cache(maxsize=4096)
def _repair(token: str,domain: str) -> str:
    forms=_DOMAINS[domain]
    if len(token)<5 or token in forms or token in _NEGATIVE_FORMS:return token
    matches=[]
    for n in (len(token)-1,len(token),len(token)+1):
        for candidate in _INDEX[domain].get(n,()):
            if _one_edit(token,candidate):
                matches.append(candidate)
                if len(matches)>1 and domain!='source':return token
    if domain=='source' and len(matches)>1:
        roots={b for b in _SOURCE_ROOTS for c in matches if c.startswith(b)}
        # Ambiguous case suffixes can share one historical-source identity.
        # This normalization supplies no subject span or grammatical ownership.
        return next(iter(roots)) if len(roots)==1 else token
    return matches[0] if matches else token

def operation_text(query: str) -> str:
    text=' '.join((query or '').translate(_FOLD).lower().split())
    # Consecutive dotted initials belong to one noun phrase. Ordinary full
    # stops still terminate ownership, including after a complete word.
    text=re.sub(r'\b(?:[a-z]\.){2,}(?=\s+[a-z])',
                lambda m: m.group().replace('.', ''), text)
    chunks=re.findall(r'[a-z]+|[^a-z]+',text)
    positions=[i for i,c in enumerate(chunks) if c.isalpha()]
    words=[chunks[i] for i in positions]
    # Clause-local prefix/suffix state keeps long requests linear in tokens.
    action_after=[False]*len(words)
    evaluation_after=[False]*len(words)
    requested=False
    evaluation=False
    for j in range(len(words)-1,-1,-1):
        action_after[j]=requested
        evaluation_after[j]=evaluation
        requested=requested or words[j].startswith(('anlat','acikla','coz'))
        evaluation=evaluation or words[j].startswith(('dogru','yanlis','degerlendir','kontrol','dogrula','incele'))
        if positions[j]>0 and re.search(r'[.!?;:]',chunks[positions[j]-1]):
            requested=False
            evaluation=False
    historical_before=False
    for j,(i,word) in enumerate(zip(positions,words)):
        if i>0 and re.search(r'[.!?;:]',chunks[i-1]):historical_before=False
        following=words[j+1:j+4]
        if following and following[0].startswith(('konu','baslik','baslig')):
            chunks[i]=_repair(word,'relationship')
        # Only repair predicates at a request boundary or before a request
        # auxiliary. Valid inflected action forms are already authoritative.
        boundary=(j==len(words)-1 or bool(re.search(r'[.!?;:]',chunks[i+1] if i+1<len(chunks) else '')))
        if boundary or any(w in ('istiyorum','misin','miyim','gibi','ve','ama','etmem','et','edin') for w in following[:1]):
            chunks[i]=_repair(word,'action')
        # Historical-source rescue requires a question/source relationship,
        # rather than modifying dental nouns such as "karisik".
        source=_repair(word,'source')
        if source!=word and (any(w.startswith(('soru','sinav','test','ayni','benzer')) for w in following) or word[:2] in ('ci','ck','ge')):
            chunks[i]=source
        # Argument rescue is grammatical: a nearby request or question binds
        # the token. Subject words in a long list are not repaired globally.
        if any(w.startswith(('kur','degerlendir','kontrol','nerede','nereye','nasil','gibi','dogrulug','dogru','yanlis','uret','hazirla','olustur','incele','istiyorum','sorul','yeni','ozetle','cikar','goster','bul')) for w in following) or (j>0 and words[j-1].startswith(('yoklanan','dayandig','gecmis','cikmis','ayni'))):
            chunks[i]=_repair(chunks[i],'argument')
        # The question noun can follow an arbitrarily long modified subject.
        # Rescue only that noun class, not all intervening subject tokens.
        if historical_before and action_after[j]:
            chunks[i]=_repair(chunks[i],'question')
        if historical_before and evaluation_after[j]:
            chunks[i]=_repair(chunks[i],'option')
        if chunks[i].startswith(('gecmis','cikmis')):historical_before=True
    return ''.join(chunks)

@dataclass(frozen=True)
class StudyOperation:
    task: str | None
    past: bool = False
    generate: bool = False
    coverage: bool = False

# Request inflections, not arbitrary root wildcards ("degerlendirmesi" is a
# subject noun; "degerlendir" is an operation). Negative verbs are not requests.
_REQUEST_END = r'(?:yin|in|sana|sene|mani|manizi|man|mam|yabilir|abilir|mek|mak|ip|yip)?\b'
def _action(clause: str,roots: str) -> bool:
    return bool(re.search(r'\b(?:'+roots+r')'+_REQUEST_END,clause)
        or re.search(r'\b(?:'+roots+r')(?:r|ir|ar|er)\s+(?:misin|misiniz)\b',clause))

def parse_study_operation(query: str) -> StudyOperation | None:
    # Quoted note content is evidence, not a request to the assistant.
    unquoted=re.sub(r'"[^"\n]*"|“[^”\n]*”|«[^»\n]*»','',query or '')
    text=operation_text(unquoted)
    negative=r'\b(?:ozetleme|uretme|hazirlama|olusturma|cozme|anlatma|ogretme|eslestirme|baglama|listeleme|ayirma|gosterme|bulma)(?:yin)?\b\s*(?=,|$|[.!?;])'
    has_negative=bool(re.search(negative,text))
    text=re.sub(r'[^.!?;]*?'+negative+r',?', '',text)
    clauses=[c.strip() for c in re.split(r'[.!?;:]\s*',text) if c.strip()]
    broad=bool(re.search(r'\b(?:tum|butun)\s+(?:not\w*|ders\w*|konu\w*|bolum\w*|baslik\w*)\b|\b(?:bastan sona|notun tamami\w*|her seyi|genel tekrar|eksiksiz|kapsamli|detayli)\b|\b(?:notu|notlari|dersi|bolumu)\s+ozetle|\bnotta\s+gecen\s+(?:tum|butun)\b',text))
    # A historical modifier can precede a long dental noun phrase. The
    # question head owns that modifier inside a clause, without a character
    # window or a list of recognized dental subject names.
    historical=bool(re.search(r'\bcikmis\w*\b|\bhoc\w*.{0,24}sor(?:mus|dugu)\w*\b',text)) or any(
        re.search(r'\bgecmis\b.*\b(?:sinav\w*|soru\w*)\b',c) for c in clauses)
    summary=any(_action(c,'ozetle|toparla|birlestir|yogunlastir|sikistir') or bool(re.search(r'\bozet\w*\b',c)) for c in clauses)
    summary = summary or any(_action(c,'donustur|cevir|sikistir|birlestir') and re.search(
        r'\b(?:tekrar kag[i]?d\w*|tekrar kagit\w*|ders fis\w*|calisma sayfa\w*)\b',c) for c in clauses)
    summary = summary or any(_action(c, 'getir|cevir|donustur') and re.search(
        r'\b(?:calisabilecegim|calisilabilir)\s+(?:bir\s+)?hale\b', c) for c in clauses)
    generation=any((_action(c,'uret|hazirla|olustur|yaz|sor|yap') and bool(re.search(r'\b(?:soru\w*|test\w*|alistirma\w*|quiz|deneme)\b',c))) or bool(re.search(r'\b(?:kendimi test|calismami sina|mini deneme|quiz)\b',c)) or bool(re.search(r'\byeni\b.*\bsoru\w*\b.*\bistiyorum\b',c)) for c in clauses)
    count_argument = STUDY_COUNT_PATTERN
    generation = generation or any(re.search(
        r'\b' + count_argument + r'\s+(?:soru|test|quiz|questions?)\s+(?:olsun|istiyorum|lazim)\b', c)
        for c in clauses)
    generation = generation or any(_action(c, 'calistir|sina')
                                  and re.search(r'\b(?:beni|bizi|kendimi)\b', c) for c in clauses)
    omitted_request = elliptical_study_request(query.split(' — ')[-1])
    generation = generation or omitted_request == 'generate_questions'
    similarity=bool(re.search(r'\b(?:benzer\w*|benzeyen\w*|ayni\s+(?:tarz\w*|tip\w*|manti[kg]\w*))\b',text))
    explain=any(_action(c,'acikla|anlat|ogret') or bool(re.search(r'\bcalisalim\b|\b(?:mantig\w*|mantik|baglanti\w*)\b.{0,48}\bkur\b|\b(?:ders|ogrenciye)\b.{0,16}\banlatir gibi\b',c)) for c in clauses)
    explain = explain or any(re.search(r'\b(?:anlamadim|anlayamadim|kafam\s+karisti)\b', c) for c in clauses)
    explain = explain or omitted_request in {'explain', 'outline'}
    explain = explain or any(_action(c, 'hazirla') and re.search(r'\b(?:beni|bizi)\b', c)
                            and re.search(r'\b(?:sinava|finale|vizeye)\b', c) for c in clauses)
    if re.search(r'\b(?:veya|yahut|ya da)\b',text) and sum((summary,generation,explain))>1:
        return StudyOperation(None)
    if historical or bool(re.search(r'\b(?:sikca|en sik|surekli|tekrarlanan|yinelenen)\b.{0,64}\b(?:soru\w*|sorul\w*|sordu\w*)\b',text)):
        if generation and similarity:return StudyOperation('similar_questions',True,True,broad)
        # Option judgment must own an option argument in the same clause.
        # "en sik" and "sik tekrar" are frequency, never an option mention.
        option=False
        for c in clauses:
            no_frequency=re.sub(r'\ben sik\b|\bsik(?: sik| tekrar|ca)\b','',c)
            argument=bool(re.search(r'\b(?:secenek\w*|oncul\w*|sik(?:lar\w*|ki\w*|k\w*)?)\b',no_frequency))
            judgment=(_action(c,'degerlendir|kontrol|gerekcelendir|incele|dogrula') or bool(re.search(r'\b(?:dogru|yanlis|dogrulug\w*)\b',c)))
            if argument and judgment:option=True
        if option:return StudyOperation('past_option_review',True,False,broad)
        repeated=bool(re.search(r'\b(?:tekrar(?: tekrar| eden|lanan)?|yinelen\w*|surekli|en sik|sikca|sik sik)\b',text))
        if repeated and not summary:return StudyOperation('repeated_patterns',True,False,True)
        # Match the topic noun's inflection and its historical relationship;
        # a generic summary with incidental exam context remains a summary.
        topic=bool(re.search(r'\b(?:dayandig\w*|bagli oldugu|yoklanan|gecen)\s+(?:konu\w*|basli[kg]\w*)\b|\bhareketle\b.{0,48}\bkonu\w*\b',text))
        topic = topic or any(re.search(r'\b(?:dayandig\w*|bagli oldugu|yoklanan|gecen)\b.*\b(?:konu\w*|basli[kg]\w*)\b',c) for c in clauses)
        topic = topic or any(re.search(r'\b(?:gecmis|cikmis)\w*\s+soru\w*(?:dan|den)\b',c) and re.search(r'\bkonu\w*\b',c) for c in clauses)
        if topic and (summary or any(_action(c,'cevir|toparla') for c in clauses)):return StudyOperation('past_topic_summary',True,False,True)
        alignment=any(bool(re.search(r'\b(?:eslestir\w*|karsilik\w*|karsilig\w*|eslesme\w*)\b',c)) or (_action(c,'bagla') and bool(re.search(r'\b(?:not\w*|sayfa\w*|bolum\w*|baslik\w*|oncul\w*)\b',c))) for c in clauses)
        if alignment:return StudyOperation('past_note_alignment',True,False,broad)
        # Solving requires an affirmative request; "cozum uydurma" is a
        # source constraint and cannot steal alignment/distribution operations.
        solve=any(_action(c,'coz') or bool(re.search(r'\b(?:dogru cevab\w*|dogru sonuc\w*|celdirici\w*)\b',c)) for c in clauses)
        solve = solve or any(_action(c,'anlat|acikla') and re.search(r'\b(?:sorusunu|soruyu|sorulari)\b',c) for c in clauses)
        if solve:return StudyOperation('past_question_explain',True,False,broad)
        distribution=bool(re.search(r'\b(?:dagilim\w*|oruntu\w*|kac sor\w*|bilgi tur\w*|kazan\w*)\b',text)) or any(_action(c,'grupla|ayir') and bool(re.search(r'\b(?:soru\w*|konu\w*)\b',c)) for c in clauses)
        if distribution and not summary:return StudyOperation('past_exam_patterns',True,False,True)
    if summary:return StudyOperation('summarize',False,generation,broad)
    if any(_action(c, 'cikar|hazirla|olustur|yap') and re.search(r'\bcalisma\s+(?:plan|program)\w*\b', c) for c in clauses):
        return StudyOperation('summarize',False,False,True)
    if generation:return StudyOperation('generate_questions',False,True,broad or bool(re.search(r'\b(?:dengeli|her konu\w*)\b',text)))
    # Salience is a requested selection, not a passing exam/persona mention.
    salience=any((_action(c,'goster|belirle|sec|ayir|cikar|bul|listele|ayikla') and bool(re.search(r'\b(?:kritik|onem\w*|oncelik\w*|sorabil\w*|sorul\w*|soru kur\w*|ezberle\w*|gozden kacir\w*)\b',c))) or bool(re.search(r'\b(?:mutlaka kontrol)\b',c)) for c in clauses)
    if broad and any(_action(c,'cikar|listele|sirala|derle|topla') and bool(re.search(r'\b(?:deger\w*|olcum\w*|oran\w*|siniflama\w*|bulgu\w*|tani\w*|tedavi\w*)\b',c)) for c in clauses):return StudyOperation('summarize',False,False,True)
    if salience or study_priority_request(query.split(' — ')[-1]):
        return StudyOperation('exam_points',False,False,True)
    if explain:return StudyOperation('explain',False,False,broad)
    if any(re.search(r'\b(?:'+ '|'.join(_ACTION_ROOTS) +r')(?:r|ir)\b',c) for c in clauses):
        return StudyOperation(None)
    if has_negative or unquoted!=(query or ''):return StudyOperation(None)
    return None
