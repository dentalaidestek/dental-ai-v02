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
    selected = blocks[:count]
    result = '\n\n'.join(([prefix] if prefix else []) + [b for _,b in selected])
    if len(selected) < count:
        result += f'\n\nBu aktarımda {len(selected)} soru verildi; istenen {count} soruya göre {count-len(selected)} soru eksik. Bu liste tamamlanmış değildir.'
    return result
