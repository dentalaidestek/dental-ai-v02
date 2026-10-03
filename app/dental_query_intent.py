"""Deterministic dental question intent classification for retrieval planning."""
from __future__ import annotations
from dataclasses import dataclass
import re

_ASCII_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

def _intent_text(query: str) -> str:
    """Normalize orthography for intent semantics, never for factual content."""
    clean = " ".join((query or "").split())
    return clean.translate(_ASCII_FOLD)


# Closed vocabulary used only to repair misspelled *question operators*.  Subject
# words are never rewritten here; entity typo recovery remains graph-scoped and
# ambiguity guarded.
_INTENT_OPERATOR_WORDS = (
    "nedir", "demektir", "tanim", "kavramini", "acikla", "anlat",
    "deger", "referans", "araligi", "olcum", "olculur", "degerlendirilir",
    "siniflama", "siniflandirilir", "evreleri",
    "tani", "teshis", "bulgulari", "semptomlari",
    "tedavi", "tedavisinde", "yonetimini",
    "komplikasyon", "komplikasyonlari", "etkileri",
    "neden", "faktorleri", "yatkinlastiran", "etkenleri",
    "endikasyonlari", "kontrendikasyonlari", "uygulanir", "uygulanmamalidir",
    "tercih", "edilmez", "anatomik", "iliskileri", "komsudur",
    "tanimlamali", "kavramsal", "aciklamayi", "senaryolarini", "kacinmam",
    "ardindan", "problemler", "olumsuz", "sonuclar", "zemin", "hazirlayan",
    "predispozan", "kategorilere", "basliklari",
    "secimini", "seceneginden", "kosullarda", "kullanimini", "durumlar",
    "tercihine", "yonelmeli", "senaryolarini", "sakincali", "sartlari",
    "gelismesini", "kolaylastiran", "kosullar", "faktorleri", "etiyolojik",
)


def _intent_edit_distance_at_most_one(left: str, right: str) -> bool:
    """One insertion/deletion/substitution or one adjacent transposition."""
    if left == right:
        return True
    if len(left) == len(right):
        diffs = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            i, j = diffs
            return left[i] == right[j] and left[j] == right[i]
        return False
    if abs(len(left) - len(right)) != 1:
        return False
    short, long = (left, right) if len(left) < len(right) else (right, left)
    i = j = edits = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        else:
            edits += 1
            j += 1
            if edits > 1:
                return False
    return True


def _repair_intent_operators(text: str) -> str:
    """Repair one-edit typos only when a token has one unique operator target."""
    tokens = re.findall(r"[a-z0-9]+|[^a-z0-9]+", text or "", flags=re.I)
    repaired = []
    for token in tokens:
        if not token.isalpha() or len(token) < 5:
            repaired.append(token)
            continue
        # Protect valid semantic heads before typo rescue. In particular,
        # "tanim" (definition) must never be rewritten to "tani" (diagnosis).
        if token in _INTENT_OPERATOR_WORDS:
            repaired.append(token)
            continue
        matches = [word for word in _INTENT_OPERATOR_WORDS if _intent_edit_distance_at_most_one(token, word)]
        repaired.append(matches[0] if len(matches) == 1 else token)
    return "".join(repaired)

@dataclass(frozen=True)
class DentalIntent:
    name: str
    preferred_kinds: tuple[str, ...]
    relation_hints: tuple[str, ...] = ()

_RULES = (
    ("value", re.compile(r"(?iu)(?:\b(?:kaç|kaçtır|değer(?!lendir)[a-zçğıöşü]*|(?:normal|referans)\s+(?:değer(?!lendir)[a-zçğıöşü]*|aral(?:ık|ığ)[a-zçğıöşü]*)|mm|oran[a-zçğıöşü]*)\b|\b(?:açı|değer|ölçüm|oran)[a-zçğıöşü]*\b.{0,32}\b(?:değiş[a-zçğıöşü]*|art[a-zçğıöşü]*|azal[a-zçğıöşü]*|trend[a-zçğıöşü]*|seyir[a-zçğıöşü]*)\b)", re.I),
     ("measurement",), ("measures", "assessed_by")),
    ("measurement", re.compile(r"\b(?:hangi açı(?:yla)?|hangi ölçüm|ölçüm mantığ[a-zçğıöşü]*|neyle ölç|nasıl ölç|nasıl ölçül|ölçül[a-zçğıöşü]*|ölçüm[a-zçğıöşü]* nasıl|neyi değerlendir[a-zçğıöşü]*|değerlendiril[a-zçğıöşü]*|değerlendir[a-zçğıöşü]*\s+(?:yapı|parametre|özellik|ilişki)[a-zçğıöşü]*|(?:hangi\s+)?(?:yapısal\s+)?(?:yapı|parametre|özellik|ilişki)[a-zçğıöşü]*.{0,24}değerlendir[a-zçğıöşü]*|ölçüm[a-zçğıöşü]*.{0,40}(?:temsil|değerlendir)[a-zçğıöşü]*.{0,32}(?:yapı|parametre|özellik|ilişki)[a-zçğıöşü]*)\b", re.I),
     ("measurement",), ("measures", "assessed_by", "used_for")),
    ("definition", re.compile(r"\b(?:nedir|ne\s+demek(?:tir)?|tanım[a-z]*|kavram[a-z]*\s+(?:acikla|anlat)|(?:kavramı|kavramini)\s+(?:acikla|anlat))\b", re.I),
     ("diagnosis", "finding", "anatomy", "measurement", "relation"), ()),
    ("classification", re.compile(r"\b(?:sınıflam[a-zçğıöşü]*|sınıflandır[a-zçğıöşü]*|class|sınıf[a-zçğıöşü]*|evre[a-zçğıöşü]*|stage|grade|derece)\b", re.I),
     ("classification", "diagnosis", "finding"), ("classified_by", "has_stage", "has_grade")),
    ("indication", re.compile(r"\b(?:endikasyon[a-zçğıöşü]*|endike(?:dir)?|ne zaman (?:kullan|uygula|yap|öner|tercih)[a-zçğıöşü]*|hangi (?:durum|koşul|şart)[a-zçğıöşü]* (?:[a-zçğıöşü]+ ){0,3}?(?:kullan|uygula|yap|öner|tercih)[a-zçğıöşü]*|kim(?:ler)?de (?:kullan|uygula|yap|öner|tercih)[a-zçğıöşü]*)\b", re.I),
     ("procedure", "material", "imaging"), ("used_for", "has_indication")),
    ("contraindication", re.compile(r"\b(?:kontrendikasyon[a-zçğıöşü]*|kontrendike|kullanılma(?:z|malı)[a-zçğıöşü]*|uygulanma(?:z|malı)[a-zçğıöşü]*|yapılma(?:z|malı)[a-zçğıöşü]*|sakınca|önerilme(?:z|meli)[a-zçğıöşü]*|tercih edilme(?:z|meli)[a-zçğıöşü]*|kim(?:ler)?de (?:kullanılmaz|uygulanmaz|yapılmaz|önerilmez)|hangi (?:durum|koşul|şart)[a-zçğıöşü]* (?:kullanılma|uygulanma|yapılma|önerilme)[a-zçğıöşü]*)\b", re.I),
     ("procedure", "material"), ("has_contraindication",)),
    ("complication", re.compile(r"\b(?:komplikasyon[a-zçğıöşü]*|risk[a-zçğıöşü]*|zarar|istenmeyen|yan etki[a-zçğıöşü]*)\b", re.I),
     ("finding", "diagnosis", "procedure"), ("has_complication", "leads_to", "associated_with")),
    ("diagnosis", re.compile(r"\b(?:tanı(?!m|M)[a-zçğıöşü]*|teşhis[a-zçğıöşü]*|ayırt|ayırıcı|bulgu[a-zçğıöşü]*|semptom[a-zçğıöşü]*|nasıl tanı(?!m)[a-zçğıöşü]*|nasıl teşhis[a-zçğıöşü]*)\b", re.I),
     ("diagnosis", "finding", "imaging"), ("manifests_as", "has_clinical_feature", "has_radiographic_feature", "differential_with")),
    ("treatment", re.compile(r"\b(?:tedavi[a-z]*|mudahale[a-z]*|yaklasim[a-z]*|yonetim[a-z]*|ne\s+yapil[a-z]*|nasil\s+tedavi[a-z]*|(?:olunca|oldugunda|gelisince)\s+(?:ne\s+)?(?:yapilir|napilir))\b", re.I),
     ("procedure", "diagnosis"), ("has_treatment", "treats", "has_procedure", "used_for")),
    ("anatomy", re.compile(r"\b(?:nerede|konum[a-zçğıöşü]*|komşu[a-zçğıöşü]*|yakın[a-zçğıöşü]*|geçer|seyreder|anatom[a-zçğıöşü]*|(?:hangi\s+)?yapı[a-zçğıöşü]*.{0,28}ilişki[a-zçğıöşü]*|anatomik\s+ilişki[a-zçğıöşü]*)\b", re.I),
     ("anatomy", "relation"), ("anatomical_relation", "part_of")),
    ("visual", re.compile(r"\b(?:radyografi(?!k)[a-zçğıöşü]{0,8}|röntgen[a-zçğıöşü]{0,6}|görüntü(?:de|den|ler|lerde|lerden|sü|sünde)?|fotoğraf(?:ta|tan|lar|larda)?|panoramik(?:te|ten|ler|lerde)?|periapikal(?:de|den|ler|lerde)?|sefalogram[a-zçğıöşü]{0,5}|opg|cbct|film|bitewing|şekil|tablo|grafik)\b", re.I),
     ("imaging", "finding", "anatomy"), ("used_for", "anatomical_relation")),
    ("comparison", re.compile(r"\b(?:fark[a-zçğıöşü]*|karşılaştır[a-zçğıöşü]*|versus|vs\.?|hangisi daha)\b", re.I),
     ("measurement", "diagnosis", "finding", "material", "procedure"), ()),
    ("cause", re.compile(r"\b(?:neden[a-z]*|nicin|sebep[a-z]*|etyoloji[a-z]*|etiyoloji[a-z]*|patogenez[a-z]*|risk\s+faktor[a-z]*|risk[a-z]*\s+(?:olusturan|artiran|hazirlayan|yatkinlastiran)\s+(?:etken|faktor|neden)[a-z]*|yatkinlastiran\s+(?:etken|faktor|neden)[a-z]*|niye|neden\s+olur|neye\s+bagli)\b", re.I),
     ("diagnosis", "finding"), ("caused_by", "has_mechanism", "has_risk_factor", "associated_with")),
)

_CAUSAL_RISK_ROLE_RE = re.compile(
    r"(?i)\b(?:risk\s+faktor[a-z]*|risk[a-z]*\s+(?:olusturan|artiran|hazirlayan|yatkinlastiran)\s+(?:etken|faktor|neden)[a-z]*)\b"
)
_EXPLICIT_ADVERSE_OUTCOME_RE = re.compile(
    r"(?iu)\b(?:komplikasyon[a-zçğıöşü]*|yan\s+etki[a-zçğıöşü]*|istenmeyen\s+(?:etki|olay|sonuç)[a-zçğıöşü]*|zarar[a-zçğıöşü]*)\b"
)
_ADVERSE_RISK_RE = re.compile(
    r"(?iu)\b(?:komplikasyon|yan\s+etki|istenmeyen\s+(?:etki|olay|sonuç))[a-zçğıöşü]*\s+risk[a-zçğıöşü]*\b"
)


# Natural academic/clinical discourse roles. These patterns describe what the
# speaker asks the notes to provide; they are independent of any dental subject.
_NATURAL_ROLE_PATTERNS = (
    ("definition", re.compile(r"(?i)\b(?:tam\s+olarak\s+ne\s+anlat[a-z]*|nasil\s+tanimla[a-z]*|tanim\s+olarak\s+ne\s+soyle[a-z]*|temel\s+kavramsal\s+aciklama[a-z]*|kavramsal\s+aciklama)\b")),
    ("value", re.compile(r"(?i)\b(?:sayisal\s+sinir|normal\s+(?:sayi|deger)|referans\s+deger|esik|normal\s+aralik)\b")),
    ("measurement", re.compile(r"(?i)\b(?:hangi\s+yontem\s+veya\s+parametreyle\s+olcul|degerlendirmesini\s+nasil\s+yap|olcerken|hangi\s+olcum\s+esas)\b")),
    ("classification", re.compile(r"(?i)\b(?:grup[a-z]*|evre[a-z]*|hangi\s+kategorilere\s+ayril[a-z]*|evreleme\s+sistemi|hangi\s+basliklari\s+(?:ver|say)|kategorilere\s+ayril)\b")),
    ("diagnosis", re.compile(r"(?i)\b(?:dusunmek\s+icin.*bulgu|suphesini\s+destekleyen\s+tanisal|tanisina\s+giderken|tanisini\s+gerekcelendirmek)\b")),
    ("treatment", re.compile(r"(?i)\b(?:yonetim\s+sirasi|onerilen\s+yaklasim|vakasinin\s+yonetimi|durumunda\s+ne\s+yapmam)\b")),
    ("complication", re.compile(r"(?i)\b(?:istenmeyen\s+sonuc|iliskili\s+(?:sorun|komplikasyon)|olumsuz\s+sonuc[a-z]*|ardindan\s+hangi\s+problem[a-z]*|sonrasinda\s+karsilasilabilecek|uygulama[a-z]*\s+ardindan.{0,28}problem)\b")),
    ("cause", re.compile(r"(?i)\b(?:gelisme[a-z]*.{0,24}kolaylastiran|ortaya\s+cikma[a-z]*.{0,16}zemin\s+hazirlayan|predispozan\s+etken|etiyolojik\s+etken|zemin\s+hazirlayan\s+faktor[a-z]*|kolaylastiran\s+(?:kosul|etken))\b")),
    ("indication", re.compile(r"(?i)\b(?:seci(?:m|mi)[a-z]*.{0,20}hangi\s+klinik\s+kosul[a-z]*|kullanim[a-z]*.{0,12}uygun\s+kilan|tercih[a-z]*.{0,16}hangi\s+durumda\s+yonel|uygun\s+kullanim\s+senaryo[a-z]*|kullanim\s+senaryo[a-z]*|uygun.{0,16}kullanim.{0,16}senaryo[a-z]*)\b")),
    ("contraindication", re.compile(r"(?i)\b(?:secene(?:k|g)[a-z]*.{0,56}(?:kacin[a-z]*|uzak\s+dur[a-z]*)|kullanim[a-z]*.{0,24}uygun\s+gormeyen|tercih[a-z]*.{0,20}etmemem\s+gereken|sakincali\s+kabul\s+edilen|hangi\s+kosul[a-z]*\s+kacin)\b")),
    ("anatomy", re.compile(r"(?i)\b(?:anatomik\s+komsuluk|bolgesinde.*yapilarla\s+iliski|anatomik\s+olarak\s+nerede|komsuluklari\s+sorulursa)\b")),
)

def classify_dental_intent(query: str) -> DentalIntent:
    clean = " ".join((query or "").split())
    intent_clean = _repair_intent_operators(_intent_text(clean))
    if _CAUSAL_RISK_ROLE_RE.search(intent_clean):
        for name, pattern, kinds, relations in _RULES:
            if name == "cause":
                return DentalIntent(name, kinds, relations)
    for name, pattern, kinds, relations in _RULES:
        if pattern.search(clean) or pattern.search(intent_clean):
            return DentalIntent(name, kinds, relations)
    return DentalIntent("general", (), ())


def classify_dental_intents(query: str, *, limit: int = 6) -> tuple[DentalIntent, ...]:
    """Return explicit question requirements without turning subject words into intents."""
    clean = " ".join((query or "").split())
    intent_clean = _repair_intent_operators(_intent_text(clean))
    found: list[DentalIntent] = []
    natural_roles = {name for name, pattern in _NATURAL_ROLE_PATTERNS if pattern.search(intent_clean)}
    for name, pattern, kinds, relations in _RULES:
        raw_match = pattern.search(clean)
        normalized_match = pattern.search(intent_clean)
        match = raw_match or normalized_match
        if not match and name not in natural_roles:
            continue
        # "kanal tedavisi komplikasyonları" names a treatment as the subject;
        # it does not ask for treatment itself. Require treatment wording to
        # behave like a requested facet, unless no stronger requested facet exists.
        if name == "treatment" and match is not None:
            # Match offsets belong to whichever orthographic view matched.
            # ASCII-normalized matches must never slice the raw string by a
            # different match object's offsets.
            source_text = clean if raw_match is not None else intent_clean
            tail = source_text[match.end():]
            if re.search(r"^\s+(?:komplikasyon|risk|yan etki|endikasyon|kontrendikasyon)", tail, re.I):
                continue
        found.append(DentalIntent(name, kinds, relations))
        if len(found) >= max(1, min(limit, 6)):
            break
    if found:
        # Risk language has two different semantic roles:
        #   antecedent factor ("risk faktörü", "riski artıran neden") -> cause
        #   adverse outcome ("komplikasyon", "yan etki", "komplikasyon riski") -> complication
        # A causal-risk phrase must suppress only the complication inferred from
        # the ambiguous word "risk"; it must never erase an independently explicit
        # adverse-outcome request in the same coordinated question.
        causal_risk = bool(_CAUSAL_RISK_ROLE_RE.search(intent_clean))
        if causal_risk and any(item.name == "cause" for item in found):
            explicit_adverse = bool(
                _EXPLICIT_ADVERSE_OUTCOME_RE.search(clean) or _ADVERSE_RISK_RE.search(clean)
            )
            if not explicit_adverse:
                found = [item for item in found if item.name != "complication"]
        # Negative applicability overrides a coincident positive applicability cue.
        # An explicit "endikasyon" word (not the one inside "kontrendikasyon") is
        # a separate request: "endikasyonları ve kontrendikasyonları".
        if any(item.name == "contraindication" for item in found) and not re.search(
            r"(?<!kontr)endikasyon", clean, re.I
        ):
            found = [item for item in found if item.name != "indication"]
        # Imaging words describe a modality/constraint surprisingly often
        # ("CBCT'de mandibular kanal ilişkisi"). When another explicit intent
        # states what is actually asked, visual must not become a second facet
        # that forces unnecessary multi-evidence retrieval or attachments.
        non_visual = [item for item in found if item.name != "visual"]
        if non_visual:
            found = non_visual
        # Generic "nedir/nelerdir" often closes a multi-facet Turkish question
        # ("tanısı ve tedavisi nedir?"). It must not create a fake definition
        # requirement when stronger explicit facets are already present.
        explicit = [item for item in found if item.name != "definition"]
        if explicit and "definition" not in natural_roles:
            found = explicit
        return tuple(found)
    return (DentalIntent("general", (), ()),)


def combined_relation_hints(intents: tuple[DentalIntent, ...], *, limit: int = 10) -> tuple[str, ...]:
    """Bounded union preserving intent priority."""
    result: list[str] = []
    for intent in intents:
        for relation in intent.relation_hints:
            if relation not in result:
                result.append(relation)
            if len(result) >= limit:
                return tuple(result)
    return tuple(result)


@dataclass(frozen=True)
class DentalRequirementPlan:
    subject_node_ids: tuple[str, ...]
    subject_terms: tuple[str, ...]
    intents: tuple[DentalIntent, ...]
    requested_facets: tuple[str, ...]
    relation_hints: tuple[str, ...]
    specialties: tuple[str, ...]
    qualifiers: tuple[str, ...] = ()
    comparison_terms: tuple[str, ...] = ()
    asks_negation: bool = False
    subject_count: int = 0
    unresolved_subject: bool = False
    constraint_node_ids: tuple[str, ...] = ()
    explicit_relations: tuple[tuple[str, str, str], ...] = ()
    subject_qualifiers: tuple[tuple[str, tuple[str, ...]], ...] = ()
    requires_visual_source: bool = False
    comparison_sides: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()

_SUBJECT_STOP_RE = re.compile(
    r"\b(?:nedir|nelerdir|kaçtır|hangisi|hangileri|anlat|açıkla|özetle|tanı(?:sı|ları|nı|yı)?|"
    r"tedavi(?:si|leri|sini)?|bulgu(?:su|ları|larını)?|semptom(?:u|ları)?|"
    r"komplikasyon(?:u|ları)?|endikasyon(?:u|ları)?|kontrendikasyon(?:u|ları)?|"
    r"sınıflama(?:sı|ları)?|etyoloji(?:si)?|etiyoloji(?:si)?|patogenez(?:i)?|"
    r"klinik|radyografik|ayırt edici|ayırıcı|değil|değildir|olmayan|olmaz|olmamalı(?:dır)?|"
    r"yapılmaz|kullanılmaz|uygulanmaz|önerilmez|tercih edilmez|kaçınılmalı(?:dır)?|"
    r"hariç|yanlıştır|peki|bunun|onun|bunların|ve|ile|ile birlikte)\b",
    re.I,
)
_SUBJECT_SUFFIX_RE = re.compile(r"(?iu)(?:nın|nin|nun|nün|ın|in|un|ün)$")

def _lexical_subject_terms(query: str, *, limit: int = 4) -> tuple[str, ...]:
    """Keep unknown dental subjects searchable without inventing graph nodes."""
    clean = re.sub(r"[?,;:()]+", " ", query or "")
    clean = _SUBJECT_STOP_RE.sub(" ", clean)
    tokens = [t.strip(".-") for t in clean.split() if len(t.strip(".-")) >= 2]
    tokens = [_SUBJECT_SUFFIX_RE.sub("", t) for t in tokens]
    tokens = [t for t in tokens if len(t) >= 2]
    if not tokens:
        return ()
    # Preserve phrase order; FTS can still tokenize it. Bounded to avoid turning
    # the entire question into a broad lexical query.
    phrase = " ".join(tokens[:8]).strip()
    return (phrase,) if phrase else ()


_QUALIFIER_PATTERNS = (
    ("maksiller", re.compile(r"\b(?:maksiller|maksilla(?:da|dan|daki|nın|nin)?)\b", re.I)),
    ("mandibular", re.compile(r"\b(?:mandibular|mandibula(?:da|dan|daki|nın|nin)?)\b", re.I)),
    ("üst", re.compile(r"\büst(?:te|ten|teki)?\b", re.I)),
    ("alt", re.compile(r"\balt(?:ta|tan|taki)?\b", re.I)),
    ("sağ", re.compile(r"\bsağ(?:da|dan|daki)?\b", re.I)),
    ("sol", re.compile(r"\bsol(?:da|dan|daki)?\b", re.I)),
    ("anterior", re.compile(r"\banterior(?:da|dan|daki)?\b", re.I)),
    ("posterior", re.compile(r"\bposterior(?:da|dan|daki)?\b", re.I)),
    ("süt", re.compile(r"\bsüt(?:te|ten|teki)?\b", re.I)),
    ("daimi", re.compile(r"\bdaimi\b", re.I)),
    ("primer", re.compile(r"\bprimer\b", re.I)),
    ("sekonder", re.compile(r"\bsekonder\b", re.I)),
    ("akut", re.compile(r"\bakut(?:ta|tan)?\b", re.I)),
    ("kronik", re.compile(r"\bkronik(?:te|ten)?\b", re.I)),
    ("reversible", re.compile(r"\breversible\b", re.I)),
    ("irreversible", re.compile(r"\birreversible\b", re.I)),
    ("semptomatik", re.compile(r"\bsemptomatik\b", re.I)),
    ("asemptomatik", re.compile(r"\basemptomatik\b", re.I)),
    ("lokalize", re.compile(r"\blokalize\b", re.I)),
    ("generalize", re.compile(r"\bgeneralize\b", re.I)),
    ("erken", re.compile(r"\berken\b", re.I)),
    ("geç", re.compile(r"\bgeç\b", re.I)),
    ("çocuk", re.compile(r"\bçocuk(?:ta|tan|larda|larda)?\b", re.I)),
    ("erişkin", re.compile(r"\berişkin(?:de|den|lerde)?\b", re.I)),
)
def query_qualifiers(query: str) -> tuple[str, ...]:
    text = query or ""
    return tuple(name for name, pattern in _QUALIFIER_PATTERNS if pattern.search(text))

def qualifier_present(qualifier: str, text: str) -> bool:
    return any(name == qualifier and pattern.search(text or "") for name, pattern in _QUALIFIER_PATTERNS)

_NEGATION_REQUEST_RE = re.compile(
    r"\b(?:değil|değildir|olmayan|olmaz|yapılmaz|kullanılmaz|uygulanmaz|"
    r"hariç|yanlıştır|yanlış olan|doğru değildir|hangisi yanlış|"
    r"önerilmez|tercih edilmez|olmamalı(?:dır)?|kaçınılmalı(?:dır)?)\b",
    re.I,
)
def _asks_negation(query: str) -> bool:
    text = (query or "").casefold()
    return bool(re.search(
        r"(?iu)\b(?:değil|değildir|olmayan|olmaz|yapılmaz|kullanılmaz|uygulanmaz|"
        r"yapılma(?:ma)?[a-zçğıöşü]*|kullanılma(?:ma)?[a-zçğıöşü]*|uygulanma(?:ma)?[a-zçğıöşü]*|"
        r"önerilme(?:me)?[a-zçğıöşü]*|tercih\s+edilme(?:me)?[a-zçğıöşü]*|"
        r"hariç|yanlış(?:tır|\s+olan)?|doğru\s+(?:değil(?:dir)?|olmayan)|önerilmez|tercih\s+edilmez|olmamalı[a-zçğıöşü]*|"
        r"kaçınılma[a-zçğıöşü]*|kaçınılmalı[a-zçğıöşü]*|kaçınmam\s+gerek[a-zçğıöşü]*|uzak\s+dur[a-zçğıöşü]*|kontrendike\s+değildir)\b",
        text,
    ))

_COMPARISON_SPLIT_RE = re.compile(r"\s+(?:ile|ve|vs\.?|versus)\s+", re.I)


def _query_qualifiers(query: str) -> tuple[str, ...]:
    return query_qualifiers(query)



def _subject_qualifier_bindings(query: str, subject_nodes) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Bind nearby explicit modifiers to explicit subjects without an NLP model."""
    text = query or ""
    mentions: list[tuple[int, int, str]] = []
    for node in subject_nodes:
        terms = sorted((node.label, *node.aliases), key=len, reverse=True)
        for term in terms:
            clean = " ".join((term or "").split())
            if not clean:
                continue
            pattern = re.escape(clean).replace(r"\ ", r"\s+")
            match = re.search(r"(?<!\w)" + pattern + r"(?!\w)", text, re.I)
            if match:
                mentions.append((match.start(), match.end(), node.id))
                break
    if not mentions:
        return ()
    bound: dict[str, list[str]] = {}
    for qualifier, pattern in _QUALIFIER_PATTERNS:
        qmatch = pattern.search(text)
        if not qmatch:
            continue
        candidates: list[tuple[int, str]] = []
        for start, end, node_id in mentions:
            if qmatch.end() <= start:
                distance = start - qmatch.end()
                between = text[qmatch.end():start]
            elif end <= qmatch.start():
                distance = qmatch.start() - end
                between = text[end:qmatch.start()]
            else:
                distance = 0
                between = ""
            if distance > 32 or re.search(r"[;.!?]", between):
                continue
            candidates.append((distance, node_id))
        candidates.sort()
        if not candidates:
            continue
        best_distance = candidates[0][0]
        best_ids = {node_id for distance, node_id in candidates if distance == best_distance}
        if len(best_ids) != 1:
            continue
        node_id = next(iter(best_ids))
        bound.setdefault(node_id, []).append(qualifier)
    return tuple((node_id, tuple(dict.fromkeys(values))) for node_id, values in bound.items())


def _comparison_terms(query: str, intents: tuple[DentalIntent, ...]) -> tuple[str, ...]:
    if not any(intent.name == "comparison" for intent in intents):
        return ()
    clean = re.sub(r"(?i)\b(?:arasındaki|fark(?:ı|ları)?|karşılaştır[a-zçğıöşü]*|hangisi daha)\b", " ", query or "")
    parts = [re.sub(r"\s+", " ", part).strip(" ?.,;:") for part in _COMPARISON_SPLIT_RE.split(clean)]
    return tuple(part for part in parts if len(part) >= 2)[:2]


def _comparison_sides(query: str, intents: tuple[DentalIntent, ...]) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    if not any(intent.name == "comparison" for intent in intents):
        return ()
    from app.dental_knowledge_graph import matched_nodes
    parts = [part.strip(" ?.,;:") for part in _COMPARISON_SPLIT_RE.split(query or "") if part.strip()]
    if len(parts) < 2:
        return ()
    sides = []
    for part in parts[:2]:
        node_ids = tuple(dict.fromkeys(node.id for node in matched_nodes(part) if node.kind != "imaging"))
        qualifiers = query_qualifiers(part)
        if node_ids or qualifiers:
            sides.append((node_ids, qualifiers))
    return tuple(sides) if len(sides) >= 2 else ()


def build_dental_requirement_plan(query: str) -> DentalRequirementPlan:
    """Separate what the user asks about from which facts they request."""
    from app.dental_knowledge_graph import matched_nodes
    clean = " ".join((query or "").split())
    intents = classify_dental_intents(clean, limit=6)
    # Normalize common Turkish genitive suffixes attached directly to Latin
    # dental terms (e.g. "pulpitisin") for entity recognition only.
    entity_query = re.sub(
        r"(?iu)(?<=[a-zçğıöşü])(?:nin|nın|nun|nün|in|ın|un|ün)(?=\s|$)",
        "",
        clean,
    )
    nodes = matched_nodes(entity_query)
    if entity_query != clean:
        # The suffix strip above turns "amoksisilin" into "amoksisil".  Keep the
        # unstripped reading as well; the stripped result stays first and wins.
        seen_ids = {node.id for node in nodes}
        nodes = [*nodes, *(node for node in matched_nodes(clean) if node.id not in seen_ids)]
    # Imaging entities constrain how/where evidence is interpreted, but they
    # are not normally an independent factual subject. Requiring CBCT/OPG as a
    # second "subject" made otherwise correct evidence fail completeness.
    subject_nodes = tuple(node for node in nodes if node.kind != "imaging")
    constraint_nodes = tuple(node for node in nodes if node.kind == "imaging")
    subject_ids = tuple(dict.fromkeys(node.id for node in subject_nodes))
    subject_terms = tuple(dict.fromkeys(node.label for node in subject_nodes))
    if not subject_terms:
        # If the query is genuinely about the imaging modality itself ("CBCT
        # nedir?"), it remains the subject; otherwise imaging stays a constraint.
        non_visual_intents = {item.name for item in intents if item.name not in {"general", "visual"}}
        if constraint_nodes and non_visual_intents.intersection({"definition", "comparison", "indication", "contraindication"}):
            subject_ids = tuple(dict.fromkeys(node.id for node in constraint_nodes))
            subject_terms = tuple(dict.fromkeys(node.label for node in constraint_nodes))
        else:
            subject_terms = _lexical_subject_terms(clean)
    specialties = tuple(dict.fromkeys(node.specialty for node in nodes if node.specialty != "general"))
    # Preserve only relations whose two endpoints were explicitly mentioned by
    # the user. The graph may explain the connection, but it must never invent
    # an unstated subject/fact for retrieval or generation.
    explicit_ids = {node.id for node in nodes}
    explicit_relations: list[tuple[str, str, str]] = []
    if len(explicit_ids) >= 2:
        from app.dental_knowledge_graph import EDGES
        from app.dental_knowledge_relations import DENTAL_RELATION_EDGES
        for edge in (*EDGES, *DENTAL_RELATION_EDGES):
            if edge.weight < 0.80:
                continue
            if edge.source in explicit_ids and edge.target in explicit_ids:
                explicit_relations.append((edge.source, edge.relation.value, edge.target))
    # Two or more explicit non-imaging subjects plus a comparative operator
    # is a comparison even when the wording does not contain "fark/karşılaştır".
    # Do not treat a plain conjunction ("SNA ve SNB değerleri") as comparison.
    if (
        len(subject_ids) >= 2
        and not any(item.name == "comparison" for item in intents)
        and re.search(r"(?iu)\b(?:hangisi|hangileri|hangisinde|daha)\b", clean)
    ):
        comparison_intent = DentalIntent("comparison", (), ("compared_with",))
        intents = tuple((*intents, comparison_intent))[:6]
    comparison_terms = _comparison_terms(clean, intents)
    requires_visual_source = bool(re.search(
        r"(?iu)(?:\b(?:bu|şu)\s+(?:radyografi(?:de|da)?|röntgen(?:de|da)?|film(?:de|da)?|görüntü(?:de|da)?|fotoğraf(?:ta|da)?|panoramik(?:te|ta)?|şekil(?:de|da)?|tablo(?:da|de)?|grafik(?:te|de)?|cbct(?:de|da)?|opg(?:de|da)?)"
        r"|\b(?:radyografideki|radyografide|filmdeki|filmde|görüntüdeki|görüntüde|görüntüsünde|fotoğraftaki|fotoğrafta|panoramikte|bitewingde|bitewing görüntüsünde|cbctde|cbct'de|opgde|opg'de|şekildeki|şekilde|tablodaki|tabloda|grafikteki|grafikte)\b"
        r"|\b(?:gösterilen|işaretli|okla\s+gösterilen|görülen)\b"
        r"|\b(?:radyografi|film|görüntü|şekil|tablo|grafik)(?:de|da)\s+(?:ne|neyi|hangi|nerede)\b)",
        clean,
    ))
    facets = tuple(intent.name for intent in intents if intent.name != "general")
    return DentalRequirementPlan(
        subject_node_ids=subject_ids,
        subject_terms=subject_terms,
        intents=intents,
        requested_facets=facets,
        relation_hints=combined_relation_hints(intents, limit=16),
        specialties=specialties,
        qualifiers=_query_qualifiers(clean),
        comparison_terms=comparison_terms,
        asks_negation=_asks_negation(clean),
        subject_count=len(subject_ids) if subject_ids else len(comparison_terms),
        unresolved_subject=not bool(subject_ids or subject_terms),
        constraint_node_ids=tuple(dict.fromkeys(node.id for node in constraint_nodes)),
        explicit_relations=tuple(dict.fromkeys(explicit_relations)),
        subject_qualifiers=_subject_qualifier_bindings(clean, subject_nodes),
        requires_visual_source=requires_visual_source,
        comparison_sides=_comparison_sides(clean, intents),
    )


_STUDY_GENERATION_RE = re.compile(
    r"\b(?:soru[a-zçğıöşü]*|test|quiz|flashcard|kart|çalışma sorusu|deneme)\b.{0,48}"
    r"\b(?:üret|hazırla|oluştur|çıkar|sor)\b|"
    r"\b(?:üret|hazırla|oluştur|çıkar)\b.{0,48}\b(?:soru[a-zçğıöşü]*|test|quiz|flashcard|kart)\b",
    re.I,
)
_STUDY_COVERAGE_RE = re.compile(
    r"\b(?:tüm|bütün|tamamı|tamamını|tamamındaki|notun tamamı|notun tamamını|notun tamamından|notun tamamındaki|dersin tamamı|her konu[a-zçğıöşü]*|bütün konu[a-zçğıöşü]*|"
    r"eksiksiz|kapsamlı|sınavlık|sınav noktaları)\b",
    re.I,
)
_STUDY_DIFFICULTY_RE = re.compile(r"\b(?:kolay|orta|zor|çok zor|ayırt edici|klinik|vaka)\b", re.I)
_STUDY_COUNT_RE = re.compile(
    r"\b(\d{1,3})(?:\s+(?:adet|kolay|orta|zor|çok zor|ayırt edici|klinik|vaka|çoktan seçmeli|açık uçlu|doğru/?yanlış)){0,4}\s+(?:soru|test|quiz|flashcard|kart)\b",
    re.I,
)


@dataclass(frozen=True)
class DentalStudyPlan:
    mode: str
    count: int | None = None
    difficulty: str | None = None
    question_types: tuple[str, ...] = ()
    coverage_required: bool = False


def classify_dental_study_plan(query: str) -> DentalStudyPlan | None:
    """Detect role-neutral academic generation requests without affecting normal QA."""
    clean = " ".join((query or "").split())
    if not _STUDY_GENERATION_RE.search(clean):
        return None
    count_match = _STUDY_COUNT_RE.search(clean)
    count = min(200, int(count_match.group(1))) if count_match else None
    difficulty_match = _STUDY_DIFFICULTY_RE.search(clean)
    kinds: list[str] = []
    lowered = clean.casefold()
    if any(term in lowered for term in ("çoktan seçmeli", "test", "mcq")):
        kinds.append("mcq")
    if any(term in lowered for term in ("açık uçlu", "klasik")):
        kinds.append("open")
    if any(term in lowered for term in ("doğru yanlış", "doğru/yanlış")):
        kinds.append("true_false")
    if any(term in lowered for term in ("flashcard", "kart")):
        kinds.append("flashcard")
    coverage = bool(_STUDY_COVERAGE_RE.search(clean))
    return DentalStudyPlan(
        mode="coverage" if coverage else "topic",
        count=count,
        difficulty=difficulty_match.group(0).casefold() if difficulty_match else None,
        question_types=tuple(dict.fromkeys(kinds)),
        coverage_required=coverage,
    )


@dataclass(frozen=True)
class AcademicStudyTaskPlan:
    task: str
    requires_past_questions: bool = False
    requires_note_evidence: bool = True
    requires_coverage: bool = False
    generate_new_questions: bool = False


_BROAD_ACADEMIC_RE = re.compile(
    r"\b(?:tüm|bütün|tamamı|baştan sona|detaylı|kapsamlı|eksiksiz|genel tekrar|"
    r"notu özetle|notları özetle|dersi özetle|konuyu detaylı|bölümü özetle|notun tamamı|notun tamamından|notun tamamındaki|"
    r"her şeyi|herşeyi)\b", re.I,
)

_ACADEMIC_STUDY_TASK_RULES = (
    ("repeated_patterns", re.compile(
        r"(?iu)(?:"
        r"\b(?:sürekli|tekrar\s+tekrar|en\s+çok|en\s+sık|sık\s+sık|sıkça|tekrarlanan|yinelenen)\b"
        r".{0,64}\b(?:sor[a-zçğıöşü]*|çıkmış|soru[a-zçğıöşü]*|konu[a-zçğıöşü]*)\b"
        r"|\b(?:soru|konu)[a-zçğıöşü]*\b.{0,48}\b(?:tekrar[a-zçğıöşü]*|yinelen[a-zçğıöşü]*|sık)\b"
        r")"
    ), True, True, True, False),
    ("similar_questions", re.compile(r"\b(?:benzer|benzeyen|benzeri|benzerini|aynı tarz|aynı tip)\b.{0,64}\b(?:soru|test|üret|hazırla|oluştur|sor)|\b(?:soru|test|çıkmış)[a-zçğıöşü]*\b.{0,48}\b(?:benzer|benzeyen|benzeri|aynı tarz|aynı tip)\b.{0,48}\b(?:üret|hazırla|oluştur|sor)[a-zçğıöşü]*\b", re.I), True, True, False, True),
    ("past_exam_patterns", re.compile(r"\b(?:çıkmış|geçmiş)\s+(?:soru|sınav)|\bhoca.{0,32}(?:sormuş|sorduğu)", re.I), True, True, True, False),
    ("exam_points", re.compile(
        r"(?iu)(?:"
        r"\b(?:sınav|sorul|sorabil|çıkma|çıkabil)[a-zçğıöşü]*\b.{0,64}\b(?:yer|nokta|konu|bilgi|kısım|başlık|bölüm|içerik)[a-zçğıöşü]*\b"
        r"|\b(?:soru|sınav)[a-zçğıöşü]*\b.{0,48}\b(?:gelme|çıkma|sorulma)[a-zçğıöşü]*\b.{0,32}\b(?:ihtimal|olasılık)[a-zçğıöşü]*\b"
        r"|\b(?:ihtimal|olasılık)[a-zçğıöşü]*\b.{0,24}\b(?:yüksek|fazla)[a-zçğıöşü]*\b.{0,48}\b(?:yer|nokta|konu|bilgi|kısım|başlık|bölüm|içerik)[a-zçğıöşü]*\b"
        r"|\b(?:önem|kritik|öncelik)[a-zçğıöşü]*\b.{0,48}\b(?:yer|nokta|konu|bilgi|kısım|başlık|bölüm|içerik)[a-zçğıöşü]*\b"
        r"|\bhoca\b.{0,48}\b(?:ne|neler)\s+sorabil[a-zçğıöşü]*\b"
        r")"
    ), False, True, True, False),
    ("explain", re.compile(r"\b(?:bu kısmı|şu kısmı|bu konuyu|bu konunun|konuyu|konunun|şu konuyu|şu konunun|burayı)\b.{0,32}\b(?:anlat|açıkla|özetle|öğret)|\b(?:anlat|açıkla|özetle|öğret)\b.{0,32}\b(?:bu kısmı|şu kısmı|bu konuyu|bu konunun|konuyu|konunun|şu konuyu|şu konunun|burayı)", re.I), False, True, False, False),
)

def classify_academic_study_task(query: str) -> AcademicStudyTaskPlan | None:
    """Plan role-neutral academic workflows while keeping factual output source-bound."""
    clean = " ".join((query or "").split())
    broad = bool(_BROAD_ACADEMIC_RE.search(clean))
    lowered = clean.casefold()
    # Extraction/condensation language has higher precedence than incidental
    # salience adjectives. "kritik ölçümleri çıkar" asks to extract a fact
    # class, not to predict exam importance. Conversely, salience requests
    # without an explicit factual class continue to the semantic task rules.
    factual_class = bool(re.search(
        r"(?iu)\b(?:değer|ölçüm|oran|sınıflama|endikasyon|kontrendikasyon|komplikasyon|"
        r"bulgu|semptom|tanı|tedavi|neden|etyoloji|etiyoloji|anatom)[a-zçğıöşü]*\b",
        clean,
    ))
    extract_action = bool(re.search(r"(?iu)\b(?:çıkar|listele|sırala|derle|topla)\w*\b", clean))
    if broad and factual_class and extract_action:
        return AcademicStudyTaskPlan("summarize", False, True, True, False)
    # A broad summary request remains a summary even when the user also asks
    # which parts are exam-important; exam-point wording is an output facet.
    if any(x in lowered for x in ("özet", "özetle")):
        generate = bool(_STUDY_GENERATION_RE.search(clean))
        # Summary wording is an explicit study task even for a selected topic.
        # Coverage is independent: whole-note language broadens retrieval;
        # compound "summarize then make questions" preserves both operations.
        return AcademicStudyTaskPlan("summarize", False, True, broad, generate)
    for task, pattern, past, notes, coverage, generate in _ACADEMIC_STUDY_TASK_RULES:
        if pattern.search(clean):
            return AcademicStudyTaskPlan(task, past, notes, coverage or broad, generate)
    study = classify_dental_study_plan(clean)
    if study:
        return AcademicStudyTaskPlan(
            "generate_questions",
            False,
            True,
            study.coverage_required,
            True,
        )
    # Broad extraction requests are summary/condensation workflows even when
    # the student says "çıkar" rather than the literal verb "özetle".
    if _BROAD_ACADEMIC_RE.search(clean):
        lowered = clean.casefold()
        extractive = any(x in lowered for x in ("çıkar", "listele", "sırala", "değer", "ölçüm"))
        task = "summarize" if any(x in lowered for x in ("özet", "özetle")) or extractive else "explain"
        return AcademicStudyTaskPlan(task, False, True, True, False)
    return None