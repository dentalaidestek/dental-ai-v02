"""Deterministic dental question intent classification for retrieval planning."""
from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class DentalIntent:
    name: str
    preferred_kinds: tuple[str, ...]
    relation_hints: tuple[str, ...] = ()

_RULES = (
    ("value", re.compile(r"\b(?:kaç|kaçtır|değer(?:i)?|normal değer|derece|mm|oran)\b", re.I),
     ("measurement",), ("measures",)),
    ("measurement", re.compile(r"\b(?:hangi açı|hangi ölçüm|neyle ölç|nasıl ölç|ölçülür|değerlendirilir)\b", re.I),
     ("measurement",), ("measures", "used_for")),
    ("definition", re.compile(r"\b(?:nedir|ne demek|tanımı|tanımla)\b", re.I),
     ("diagnosis", "finding", "anatomy", "measurement", "relation"), ()),
    ("classification", re.compile(r"\b(?:sınıflama|sınıflandır|class|sınıf|evre|stage|grade|derece)\b", re.I),
     ("classification", "diagnosis", "finding"), ("classified_by",)),
    ("indication", re.compile(r"\b(?:endikasyon|ne zaman kullan|hangi durumda kullan)\b", re.I),
     ("procedure", "material", "imaging"), ("used_for",)),
    ("contraindication", re.compile(r"\b(?:kontrendikasyon|kullanılmaz|yapılmaz|sakınca)\b", re.I),
     ("procedure", "material"), ()),
    ("complication", re.compile(r"\b(?:komplikasyon|risk|zarar|istenmeyen|yan etki)\b", re.I),
     ("finding", "diagnosis", "procedure"), ("associated_with",)),
    ("diagnosis", re.compile(r"\b(?:tanı|teşhis|ayırt|ayırıcı|bulgu|semptom)\b", re.I),
     ("diagnosis", "finding", "imaging"), ("associated_with",)),
    ("treatment", re.compile(r"\b(?:tedavi|tedavisi|müdahale|yaklaşım|yönetim)\b", re.I),
     ("procedure", "diagnosis"), ("used_for",)),
    ("anatomy", re.compile(r"\b(?:nerede|konum|komşu|ilişki|yakın|geçer|seyreder|anatom)\b", re.I),
     ("anatomy", "relation"), ("anatomical_relation", "part_of")),
    ("visual", re.compile(r"\b(?:radyografi|röntgen|film|görüntü|fotoğraf|panoramik|opg|cbct|periapikal|bitewing|sefalogram|şekil|tablo|grafik)\b", re.I),
     ("imaging", "finding", "anatomy"), ("used_for", "anatomical_relation")),
    ("comparison", re.compile(r"\b(?:fark|karşılaştır|versus|vs\.?|hangisi daha)\b", re.I),
     ("measurement", "diagnosis", "finding", "material", "procedure"), ()),
    ("cause", re.compile(r"\b(?:neden|niçin|sebep|etyoloji|etiyoloji|patogenez)\b", re.I),
     ("diagnosis", "finding"), ("associated_with",)),
)

def classify_dental_intent(query: str) -> DentalIntent:
    clean = " ".join((query or "").split())
    for name, pattern, kinds, relations in _RULES:
        if pattern.search(clean):
            return DentalIntent(name, kinds, relations)
    return DentalIntent("general", (), ())
