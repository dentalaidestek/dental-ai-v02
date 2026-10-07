"""Closed grammatical output slots and conversational repair speech acts.

No medical noun fuzzing. Unconsumed nouns must remain available to topic parsing.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
REPAIR_RESPONSE = ('Yanıt beklentini karşılamamış. Önceki ders veya konu bağlamını koruyorum. '
                   'Hangi kısmı düzeltmemi istediğini söyle; örneğin atladığım başlıkları '
                   'tamamlayabilir veya anlatımı daha açık hale getirebilirim.')


def control_text(query: str) -> str:
    text = ' '.join((query or '').translate(_FOLD).lower().split()).strip(' .!?')
    text = re.sub(r'^(?:(?:kral|hocam|abi|dostum|baskan|ya|lutfen|bana|simdi)[,;:]?\s+){1,3}', '', text)
    # Colloquial determiner, not a correction of an arbitrary noun.
    text = re.sub(r'\bbi\b', 'bir', text)
    # One keyboard-neighbor error only in the paragraph output-manner slot.
    text = re.sub(r'\boaragraf(?=la\b)', 'paragraf', text)
    return text


def conversational_repair(query: str) -> bool:
    text = control_text(query)
    return bool(re.fullmatch(
        r'(?:sen\s+)?dalga\s+mi\s+geciy(?:or|o)?sun'
        r'|(?:sen\s+)?beni\s+anlamiy(?:or)?sun'
        r'|(?:yine\s+)?(?:ayni|alakasiz|yanlis)\s+(?:seyi|cevabi|cevap)\s+'
        r'(?:yazip\s+duruyorsun|verdin|verdiniz|yazdin)'
        r'|(?:ben\s+)?(?:bunu|bu\s+cevabi|boyle)\s+istemedim'
        r'|ne\s+diy(?:or)?sun(?:\s+ya)?', text))


@dataclass(frozen=True)
class OutputSlots:
    kind: str
    output_format: str | None = None
    sentences: int | None = None


def output_slots(query: str) -> OutputSlots | None:
    """Recognize omitted-subject scope + manner + action compositions."""
    text = control_text(query)
    # Feedback followed by a task is a task; bare feedback is conversational.
    clauses = [part.strip() for part in re.split(r'[.!?;,]+', text) if part.strip()]
    if len(clauses) > 1 and all(conversational_repair(part) for part in clauses[:-1]):
        text = clauses[-1]
    elif 1 < len(clauses) <= 3:
        parts = [output_slots(part) for part in clauses]
        if all(part is not None for part in parts):
            # Compose complete task clauses; the final requested format wins.
            # Any unconsumed noun rejects this branch and stays a real subject.
            return parts[-1]
    scope = (r'(?:(?:tek\s+tek\s+)?(?:her|tum|butun|diger|kalan)\s+'
             r'(?:baslik|basligi|basliklari|basliklar|konu|konuyu|konulari|konular|konulara)'
             r'|baslik\s+baslik|basliklari|hepsini)')
    action = r'(?:anlat|acikla|ogret|goster|yaz|git|gec|atlama)(?:sana|sene|in|ir)?(?:\s+misin)?'
    manner = (r'(?:(?:da|de|icin|tek|bir|ayri|kisa|madde|tane|olarak|halinde|seklinde)'
              r'|(?:paragrafla|paragraf|cumleyle|cumle|tablo|detayli|ayrintili|sirayla|tek)|\d{1,2})')
    if re.fullmatch(scope + r'\s+(?:' + manner + r'\s+)*' + action, text):
        count = re.search(r'\b(\d{1,2})\s+cumle(?:yle)?\b', text)
        fmt = ('paragraph' if 'paragraf' in text else 'table' if 'tablo' in text
               else 'bullets' if 'madde' in text else None)
        return OutputSlots('outline', fmt, int(count.group(1)) if count else None)
    # Comprehension/style repairs with an omitted object. Named nouns cannot
    # match these complete constructions and are not removed from retrieval.
    if re.fullmatch(
        r'(?:(?:hic|hicbir)\s+(?:bir\s+sey|bisey|sey)\s+)?(?:anlamadim|anlamiyom|anlamiyorum)'
        r'|kafama\s+oturmadi|(?:bu\s+anlattigin\s+)?kafami\s+karistirdi'
        r'|(?:burayi|bunu|sunu|bu\s+kismi)\s+anlamadim'
        r'|(?:cok\s+)?hizli\s+gectin|(?:anlatimin\s+)?(?:cok\s+)?yuzeysel'
        r'|(?:(?:sunu|bunu|burayi)\s+)?(?:tane\s+tane|adam\s+gibi|ornekle|'
        r'cocuga\s+anlatir\s+gibi|bir\s+daha)\s+(?:anlat|acikla)(?:ir\s+misin|sana|sene)?'
        r'|bunu\s+(?:biraz\s+)?ac|daha\s+(?:anlasilir|basit|sade)\s+olsun'
        r'|ezber\s+degil\s+mantigini\s+anlat'
        r'|kisa\s+kesme\s+ayrintiya\s+gir'
        r'|(?:neden|niye)\s+boyle|nerede\s+kullaniyoruz', text):
        return OutputSlots('explain')
    # Positive quiz controls; count/format are handled by the existing planner.
    if re.fullmatch(r'(?:(?:bir|\d{1,3})\s+)?(?:tane\s+)?(?:zor\s+)?'
                    r'(?:bir\s+)?soru\s+sor(?:\s+cevabimi\s+bekle)?'
                    r'|sirayla\s+soru\s+sor|beni\s+(?:bir\s+)?(?:dene|test\s+et)', text):
        return OutputSlots('generate_questions')
    return None


def output_slot_rules(query: str) -> str:
    slots = output_slots(query.split(' — ')[-1])
    if not slots:
        return ''
    rules = []
    if slots.kind == 'outline':
        rules.append('Başlık kapsamı: getirilen kanıttaki başlıkları ayrı işle; atlama.')
    if slots.output_format == 'paragraph':
        rules.append('Biçim: her başlık için ayrı tek paragraf yaz.')
    elif slots.output_format == 'table':
        rules.append('Biçim: başlık ve açıklama sütunları olan bir tablo kullan.')
    elif slots.output_format == 'bullets':
        rules.append('Biçim: açıklamaları madde madde ver.')
    if slots.sentences:
        rules.append(f'Biçim: her başlık için {slots.sentences} cümle kullan.')
    return '\n'.join(rules)
