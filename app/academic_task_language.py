"""Clause-scoped study operations, separate from dental subjects and evidence.

This layer reads requested transformations. It does not recognize dental entities,
repair their names, infer missing subjects, or validate factual answers.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import re

_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
# Orthographic rescue is limited to grammar/operators, with unique one-edit
# targets. Productive nominal inflections preserve the operation's argument.
_ACTION_ROOTS = frozenset(('acikla anlat ogret ozetle toparla birlestir yogunlastir sikistir '
    'uret hazirla olustur yaz cikar listele ayir grupla goster belirt bul belirle '
    'coz eslestir bagla degerlendir kontrol incele kur cevir yap sec ayikla').split())
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
    'nin','nun','ta','te','tan','ten','da','de','dan','den','si','sini','sinin','ki')
_DOMAINS = {
    'relationship': frozenset(('dayandigi','bagli','yoklanan','gecen','hareketle')),
    'action': frozenset(b+s for b in _ACTION_ROOTS for s in _REQUEST_SUFFIXES),
    'source': frozenset(b+s for b in _SOURCE_ROOTS for s in _NOUN_SUFFIXES),
    'argument': frozenset(b+s for b in _NOUN_ROOTS for s in _NOUN_SUFFIXES) | frozenset((
        'karsiligi','karsiligini','karsiligina','karsiliklari','siklarini','siklarinin',
        'siklarin','siklarina','siklarindan','mantigini','mantigi','mantiginin',
        'baglantisini','baglantiyi','baglantilari','baglantilarini','dogru','cevabina',
        'cevabi','cevabin','cevabini','cevabinin','dogrulugunu','anlatir')),
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
    chunks=re.findall(r'[a-z]+|[^a-z]+',text)
    positions=[i for i,c in enumerate(chunks) if c.isalpha()]
    words=[chunks[i] for i in positions]
    for j,(i,word) in enumerate(zip(positions,words)):
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
        if any(w.startswith(('kur','degerlendir','kontrol','nerede','nereye','nasil','gibi','dogrulug','yanlis','uret','hazirla','olustur','incele','istiyorum','sorul','yeni')) for w in following) or (j>0 and words[j-1].startswith(('yoklanan','dayandig','gecmis','cikmis'))):
            chunks[i]=_repair(chunks[i],'argument')
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
    historical=bool(re.search(r'\b(?:cikmis\w*|gecmis\s+(?:sinav\w*|soru\w*)|hoc\w*.{0,24}sor(?:mus|dugu)\w*)\b',text))
    summary=any(_action(c,'ozetle|toparla|birlestir|yogunlastir|sikistir') or bool(re.search(r'\bozet\w*\b',c)) for c in clauses)
    generation=any((_action(c,'uret|hazirla|olustur|yaz') and bool(re.search(r'\b(?:soru\w*|test\w*|alistirma\w*|quiz|deneme)\b',c))) or bool(re.search(r'\b(?:kendimi test|calismami sina|mini deneme|quiz)\b',c)) or bool(re.search(r'\byeni\b.*\bsoru\w*\b.*\bistiyorum\b',c)) for c in clauses)
    similarity=bool(re.search(r'\b(?:benzer\w*|benzeyen\w*|ayni\s+(?:tarz\w*|tip\w*|mantik\w*))\b',text))
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
            judgment=(_action(c,'degerlendir|kontrol|gerekcelendir|incele') or bool(re.search(r'\b(?:dogru|yanlis|dogrulug\w*)\b',c)))
            if argument and judgment:option=True
        if option:return StudyOperation('past_option_review',True,False,broad)
        repeated=bool(re.search(r'\b(?:tekrar(?: tekrar| eden|lanan)?|yinelen\w*|surekli|en sik|sikca|sik sik)\b',text))
        if repeated and not summary:return StudyOperation('repeated_patterns',True,False,True)
        # Match the topic noun's inflection and its historical relationship;
        # a generic summary with incidental exam context remains a summary.
        topic=bool(re.search(r'\b(?:dayandig\w*|bagli oldugu|yoklanan|gecen)\s+(?:konu\w*|basli[kg]\w*)\b|\bhareketle\b.{0,48}\bkonu\w*\b',text))
        topic = topic or any(re.search(r'\b(?:gecmis|cikmis)\w*\s+soru\w*(?:dan|den)\b',c) and re.search(r'\bkonu\w*\b',c) for c in clauses)
        if topic and (summary or any(_action(c,'cevir|toparla') for c in clauses)):return StudyOperation('past_topic_summary',True,False,True)
        alignment=any(bool(re.search(r'\b(?:eslestir\w*|karsilik\w*|karsilig\w*|eslesme\w*)\b',c)) or (_action(c,'bagla') and bool(re.search(r'\b(?:not\w*|sayfa\w*|bolum\w*|baslik\w*|oncul\w*)\b',c))) for c in clauses)
        if alignment:return StudyOperation('past_note_alignment',True,False,broad)
        # Solving requires an affirmative request; "cozum uydurma" is a
        # source constraint and cannot steal alignment/distribution operations.
        solve=any(_action(c,'coz') or bool(re.search(r'\b(?:dogru cevab\w*|dogru sonuc\w*|celdirici\w*)\b',c)) for c in clauses)
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
