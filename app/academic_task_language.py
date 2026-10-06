"""Clause-scoped study operations, separate from dental subjects and evidence.

This layer reads requested transformations. It does not recognize dental entities,
repair their names, infer missing subjects, or validate factual answers.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import re

_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')

_COURSE_SOURCE_RE = re.compile(
    r'\b(?:(?:bu|tum|butun)\s+)?(?:ders\s+)?'
    r'(?:not(?:lar)?(?:u|unu|un|ta|tan|taki|i|ini|larini|dan|indan|larindan|indaki|larindaki|da|larda|larin|imi|imdan)?'
    r'|ders(?:in\s+tamam(?:i|ini|indan)|i|in))\b'
)

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
    text = (query or '').translate(_FOLD).lower()
    text = ' '.join(text.split())
    source = _COURSE_SOURCE_RE.search(text)
    if source is None:
        return False
    prefix = text[:source.start()].strip(' ,.!?')
    if prefix and not re.fullmatch(r'(?:lutfen|bana|simdi|peki)(?:\s+(?:lutfen|bana|simdi|peki))*', prefix):
        return False
    tail = text[source.end():]
    action = re.search(r'\b(?:ozetle|toparla|acikla|anlat|ogret|hazirla|uret|olustur|yaz|cikar|listele|sirala)\w*\b', tail)
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
        r'|\b(?:coktan\s+secmeli|acik\s+uclu|dogru\s+yanlis)\b',
        ' ', argument,
    )
    tokens = re.findall(r'\w+', argument)
    modifiers = {
        'konu', 'konuyu', 'konulari', 'konularini', 'icerigi', 'icerigini',
        'bana', 'benim', 'icin', 've', 'bir', 'sekilde', 'olarak',
        'kisa', 'kisaca', 'detayli', 'ayrintili', 'basit', 'sade',
        'yuksek', 'verimli', 'zor', 'zorlayici', 'kolay', 'orta',
        'soru', 'sorular', 'sorulari', 'test', 'tane', 'adet',
    }
    return all(token in modifiers or token.isdigit() for token in tokens)
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
        or re.search(r'\b(?:'+roots+r')(?:r|ir)\s+(?:misin|misiniz)\b',clause))

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
    generation=any((_action(c,'uret|hazirla|olustur|yaz') and bool(re.search(r'\b(?:soru\w*|test\w*|alistirma\w*|quiz|deneme)\b',c))) or bool(re.search(r'\b(?:kendimi test|calismami sina|mini deneme|quiz)\b',c)) or bool(re.search(r'\byeni\b.*\bsoru\w*\b.*\bistiyorum\b',c)) for c in clauses)
    similarity=bool(re.search(r'\b(?:benzer\w*|benzeyen\w*|ayni\s+(?:tarz\w*|tip\w*|manti[kg]\w*))\b',text))
    explain=any(_action(c,'acikla|anlat|ogret') or bool(re.search(r'\b(?:mantig\w*|mantik|baglanti\w*)\b.{0,48}\bkur\b|\b(?:ders|ogrenciye)\b.{0,16}\banlatir gibi\b',c)) for c in clauses)
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
    if generation:return StudyOperation('generate_questions',False,True,broad or bool(re.search(r'\b(?:dengeli|her konu\w*)\b',text)))
    # Salience is a requested selection, not a passing exam/persona mention.
    salience=any((_action(c,'goster|belirle|sec|ayir|cikar|bul|listele|ayikla') and bool(re.search(r'\b(?:kritik|onem\w*|oncelik\w*|sorabil\w*|sorul\w*|soru kur\w*|ezberle\w*|gozden kacir\w*)\b',c))) or bool(re.search(r'\b(?:mutlaka kontrol)\b',c)) for c in clauses)
    if broad and any(_action(c,'cikar|listele|sirala|derle|topla') and bool(re.search(r'\b(?:deger\w*|olcum\w*|oran\w*|siniflama\w*|bulgu\w*|tani\w*|tedavi\w*)\b',c)) for c in clauses):return StudyOperation('summarize',False,False,True)
    if salience:return StudyOperation('exam_points',False,False,True)
    if explain:return StudyOperation('explain',False,False,broad)
    if any(re.search(r'\b(?:'+ '|'.join(_ACTION_ROOTS) +r')(?:r|ir)\b',c) for c in clauses):
        return StudyOperation(None)
    if has_negative or unquoted!=(query or ''):return StudyOperation(None)
    return None
