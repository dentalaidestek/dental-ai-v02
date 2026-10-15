"""Question-set checks independent of the model's promise to count correctly."""
import re
import unicodedata
from difflib import SequenceMatcher

_HEADING = re.compile(r'(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?Soru\s+(\d+)\s*(?:\*\*)?\s*[:.)-]?\s*(.*)$')
_OPTION = re.compile(r'(?im)(?:^|\s)[A-Ea-e][.)]\s+')


def question_blocks(answer):
    matches = list(_HEADING.finditer(answer))
    return [(int(m.group(1)), answer[m.start():matches[i+1].start() if i+1<len(matches) else len(answer)].strip())
            for i,m in enumerate(matches)]


def question_stem(block):
    text = _HEADING.sub(lambda m: m.group(2), block, count=1)
    text = _OPTION.split(text, maxsplit=1)[0]
    text = unicodedata.normalize('NFKD', text.casefold().replace('ı','i'))
    return ' '.join(re.findall(r'\w+', ''.join(c for c in text if not unicodedata.combining(c))))


def same_question(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    # Keep numbers and polarity. Changing a threshold or asking the inverse
    # can be a different question; punctuation and a few filler words are not.
    if re.findall(r'\d+',a) != re.findall(r'\d+',b):
        return False
    negative={'yanlis','yanlistir','degil','degildir','haric'}
    if bool(set(a.split()) & negative) != bool(set(b.split()) & negative):
        return False
    return min(len(a.split()),len(b.split())) >= 8 and SequenceMatcher(None,a,b,autojunk=False).ratio() >= .88


def prior_questions(history):
    return [block for item in (history or [])[-8:] if str(item.get('role','')).upper()=='ASSISTANT'
            for _,block in question_blocks(item.get('content') or '')]


def question_set_issues(answer, count, history):
    blocks = question_blocks(answer)
    issues = []
    if type(count) is int and (len(blocks) != count or [n for n,_ in blocks] != list(range(1,count+1))):
        issues.append(f'İstenen {count} soru, bulunan {len(blocks)}; sıra 1–{count} olmalı.')
    old = [question_stem(b) for b in prior_questions(history)]
    seen = []
    for number,block in blocks:
        stem = question_stem(block)
        if any(same_question(stem,p) for p in old+seen):
            issues.append(f'Soru {number}: önceki setteki veya bu setteki soru tekrarı.')
        seen.append(stem)
    return issues


def limit_source_questions(answer, count):
    """Apply a source-list count once, after every section is collected.

    Original source numbers are identities, not the requested output count.
    Never re-number a verbatim source question or invent missing choices.
    """
    blocks = question_blocks(answer)
    if type(count) is not int or count < 1:
        return answer
    if not blocks:
        return answer + f'\n\nİstenen {count} soruluk aktarım tamamlanamadı; soru listesi doğrulanamadı.'
    prefix = answer[:_HEADING.search(answer).start()].strip()
    # Source PDFs can contain several photographs of the same exam sheet.
    # Count exact transcriptions once, while keeping variants (including a
    # changed choice or unreadable portion) separate. Fuzzy practice-question
    # matching is deliberately inappropriate for verbatim source material.
    unique = []
    seen = set()
    duplicates = 0
    for number, block in blocks:
        heading = _HEADING.search(block)
        inline = heading.group(2)
        if re.fullmatch(r'\([^\n)]*\.pdf,\s*Sayfa\s+[\d,–\-\s]+\)', inline, re.I):
            inline = ''
        body = inline + '\n' + block[heading.end():]
        body = '\n'.join(line for line in body.splitlines()
                         if not re.match(r'^\s*(?:\*\*)?Kaynak(?:lar)?\s*:', line, re.I))
        key = ' '.join(unicodedata.normalize('NFC', body).split())
        if 'okunamad' in key.casefold():
            # Identical placeholders are not evidence of identical originals.
            unique.append((number, block))
            continue
        if key and key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append((number, block))
    selected = unique[:count]
    result = '\n\n'.join(([prefix] if prefix else []) + [b for _,b in selected])
    if duplicates:
        result += f'\n\nAynı metne sahip {duplicates} soru kopyası istenen adede yeniden sayılmadı.'
    if len(selected) < count:
        result += f'\n\nBu aktarımda {len(selected)} soru verildi; istenen {count} soruya göre {count-len(selected)} soru eksik. Bu liste tamamlanmış değildir.'
    return result


def question_repair_slots(answer, count, history):
    """Keep valid new questions; request only missing/repeated positions."""
    accepted={}
    old=[question_stem(b) for b in prior_questions(history)]
    for number,block in question_blocks(answer):
        if number<1 or number>count or number in accepted:
            continue
        stem=question_stem(block)
        if any(same_question(stem,p) for p in old+[question_stem(b) for b in accepted.values()]):
            continue
        accepted[number]=block
    return accepted,[n for n in range(1,count+1) if n not in accepted]


def merge_question_replacements(accepted, missing, answer):
    replacements=question_blocks(answer)
    if len(replacements)!=len(missing) or [n for n,_ in replacements]!=list(range(1,len(missing)+1)):
        raise ValueError('invalid replacement question count')
    merged=dict(accepted)
    for target,(_,block) in zip(missing,replacements):
        match=_HEADING.search(block)
        body=(match.group(2)+'\n'+block[match.end():].lstrip()).strip()
        merged[target]=f'### Soru {target}\n{body}'
    return '\n\n'.join(merged[n] for n in sorted(merged))
