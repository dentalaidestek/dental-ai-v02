"""Conservative single-call route without answer or synonym inference."""
import re


def direct_request(question, history):
    from app.academic_request_understanding import StudyRequest
    match = re.fullmatch(
        r"\s*([\wçğıöşüÇĞİÖŞÜ .()'’\-]{1,120}?)\s+(nedir|ne demek|neyi gösterir)\s*[?!.]*\s*",
        question or '', re.IGNORECASE,
    )
    if not match:
        return structured_local_request(question, history)
    subject = match.group(1).strip()
    words = re.findall(r'[^\W_]+', subject.casefold())
    if not words or len(words) > 6:
        return None
    if subject.casefold() in {'bu', 'bunun', 'o', 'onun', 'bunlar', 'onlar'}:
        for turn in reversed((history or [])[-8:]):
            if str(turn.get('role', '')).casefold() != 'user':
                continue
            prior = direct_request(turn.get('content', ''), [])
            if prior is None:
                return None
            subject = prior.retrieval_queries[0]
            break
        else:
            return None
    elif any(word in {'ve', 'ile', 'ama', 'fark', 'farkı', 'hepsi', 'tüm', 'bütün',
                      'bunlar', 'onlar', 'bu', 'o', 'soru', 'cevap', 'değil', 'hariç'} for word in words):
        return None
    return StudyRequest(f'{subject} {match.group(2)}?', 'explain', 'topic',
                        None, None, '', (subject,))


def source_marker(task):
    import base64
    import json
    data = {key: task[key] for key in ('operation', 'scope', 'retrieval_queries', 'source_sections', 'resolved_query', 'source_kind') if key in task}
    encoded = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
    return '<!--ACADEMIC_SOURCE_REQUEST:' + encoded + '-->'


def previous_source_request(history):
    import base64
    import json
    for turn in reversed((history or [])[-8:]):
        if str(turn.get('role', '')).casefold() != 'assistant':
            continue
        matches = re.findall(r'<!--ACADEMIC_SOURCE_REQUEST:([A-Za-z0-9_=-]{1,64000})-->', turn.get('content', ''))
        if not matches:
            continue
        try:
            data = json.loads(base64.urlsafe_b64decode(matches[-1]).decode())
            phrases = data.get('retrieval_queries')
            sections=data.get('source_sections',[])
            if (data.get('scope') not in {'topic', 'course'} or not isinstance(phrases, list)
                    or len(phrases) > 16 or any(not isinstance(x, str) or len(x) > 160 for x in phrases)
                    or not isinstance(data.get('resolved_query'), str)
                    or len(data['resolved_query']) > 8000 or not isinstance(sections,list)
                    or len(sections)>16 or any(not isinstance(x,str) or len(x)>400 for x in sections)):
                return None
            return data
        except (ValueError, TypeError, AttributeError, UnicodeError):
            return None
    return None


_FOLD = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')


def _explicit_subject(value):
    subject = value.strip(' .?!')
    words = re.findall(r'[^\W_]+', subject.translate(_FOLD).casefold())
    # Reject leftover task/control language instead of silently treating it as
    # a dental subject. Clinical nouns and values are preserved verbatim.
    if not words or len(words) > 16 or len(subject) > 160:
        return None
    if any(word in {'ama','veya','degil','haric','yerine','sonra','once','sadece',
                    'anlat','acikla','ogret','ozetle','hazirla','soru','cevap',
                    'bu','o','bunlar','onlar','bunu','bunlari','hepsini','her',
                    'tum','butun','hangi','neden','nasil','niye','ne'} for word in words):
        return None
    return subject


def structured_local_request(question, history):
    """Reuse existing task grammar only for complete, unambiguous compositions.

    Topic, operation, scope and requested count must all be accounted for.
    Unrecognized modifiers/clauses fall through to Gemini, not a local guess.
    """
    from app.academic_request_understanding import StudyRequest
    from app.academic_task_language import parse_study_operation
    from app.academic_request_slots import output_slots
    text = (question or '').strip().rstrip('?! .')
    if not text or len(text) > 2000 or any(char in text for char in ';\n:'):
        return None
    previous = previous_source_request(history)
    if (previous and previous.get('source_kind') == 'notes'
            and (previous['scope'] == 'course' or previous['retrieval_queries'])):
        slots = output_slots(text)
        if slots is not None:
            operation = ('generate_questions' if slots.kind == 'generate_questions' else 'explain')
            return StudyRequest(previous['resolved_query'] + ' — Güncel istek: ' + question,
                operation, previous['scope'], None, None, '',
                tuple(previous['retrieval_queries']))
    if previous and previous.get('source_kind') == 'notes' and (previous['scope'] == 'course' or previous['retrieval_queries']):
        folded = text.translate(_FOLD).casefold()
        if re.fullmatch(r'(?:(?:bunu|bunlari|hepsini)\s+)?(?:kodla|ezberlemek icin kodlama yap)'
                        r'|kodlama yap (?:bunu|bunlari|hepsini) kolay ezberleyeyim', folded):
            return StudyRequest(previous['resolved_query'] + ' — Güncel istek: ' + question,
                'teach', previous['scope'], None, None, '', tuple(previous['retrieval_queries']))
    # Independent comparison sides are separate source searches. Do not merge
    # them into a single AND query that requires one chunk to contain both.
    comparison = re.fullmatch(r"(.{1,160}?)\s+(?:ile|ve)\s+(.{1,160}?)\s+"
        r"(?:(?:arasındaki|arasindaki)\s+)?(?:farklarını|farklarini|farkını|farkini|farkları|farklari)"
        r"(?:\s+(?:anlat|açıkla|acikla|karşılaştır|karsilastir))?", text, re.I)
    if comparison:
        subjects = tuple(_explicit_subject(value) for value in comparison.groups())
        if all(subjects):
            return StudyRequest(question, 'compare', 'topic', None, None, '', subjects)
        return None
    # Task forms are generic across subjects. The existing grammar decides the
    # operation; these boundaries account for every word around its object.
    instruction = re.fullmatch(r"(.{1,160}?)\s+"
        r"(?:(kısaca|kisaca|detaylı|detayli|ayrıntılı|ayrintili|basitçe|basitce|"
        r"tablo halinde|madde madde)\s+)?"
        r"(anlat|açıkla|acikla|özetle|ozetle|öğret|ogret)(?:\s+misin)?", text, re.I)
    if instruction:
        subject = _explicit_subject(instruction.group(1))
        parsed = parse_study_operation(text)
        if parsed is None or parsed.past or parsed.generate:
            return None
        scope, searches = 'topic', (subject,) if subject else ()
        if subject is None:
            referent = instruction.group(1).translate(_FOLD).casefold()
            if not (referent in {'bunu','bunlari','hepsini','onlari','o konuyu','bu konuyu'}
                    and previous and previous.get('source_kind') == 'notes'
                    and (previous['scope']=='course' or previous['retrieval_queries'])):
                return None
            scope, searches = previous['scope'], tuple(previous['retrieval_queries'])
        if subject and re.search(r'\b(?:ve|ile)\b',subject,re.I):
            return None
        operation = 'summarize' if parsed.task == 'summarize' else 'teach' if instruction.group(3).casefold() in {'öğret','ogret'} else 'explain'
        depth = 'detailed' if instruction.group(2) in {'detaylı','detayli','ayrıntılı','ayrintili'} else 'standard'
        resolved = question if subject else previous['resolved_query'] + ' — Güncel istek: ' + question
        return StudyRequest(resolved,operation,scope,None,None,'',searches,depth=depth)
    generation = re.fullmatch(r"(.{1,160}?)\s+(?:(?:hakkında|hakkinda|konusundan)\s+)?"
        r"(\d{1,3})\s+(?:(zor|kolay|orta)\s+)?(?:(?:tane|adet)\s+)?"
        r"soru\s+(?:hazırla|hazirla|üret|uret|sor)", text, re.I)
    if generation:
        subject = re.sub(r'\s+(?:hakkında|hakkinda|konusundan)$','',generation.group(1),flags=re.I)
        subject = _explicit_subject(subject)
        parsed = parse_study_operation(text)
        count = int(generation.group(2))
        if subject is not None and parsed is not None and parsed.generate and not parsed.past and 1 <= count <= 200:
            return StudyRequest(question,'generate_questions','topic',count,generation.group(3),'',(subject,))
    return None
