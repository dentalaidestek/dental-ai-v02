"""Conservative single-call route without answer or synonym inference."""
import re


def direct_request(question, history):
    from app.academic_request_understanding import StudyRequest
    match = re.fullmatch(
        r"\s*([\wçğıöşüÇĞİÖŞÜ .()'’\-]{1,120}?)\s+(nedir|ne demek|neyi gösterir)\s*[?!.]*\s*",
        question or '', re.IGNORECASE,
    )
    if not match:
        return None
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
    data = {key: task.get(key) for key in ('operation', 'scope', 'retrieval_queries', 'resolved_query')}
    encoded = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
    return '<!--ACADEMIC_SOURCE_REQUEST:' + encoded + '-->'


def previous_source_request(history):
    import base64
    import json
    for turn in reversed((history or [])[-8:]):
        if str(turn.get('role', '')).casefold() != 'assistant':
            continue
        matches = re.findall(r'<!--ACADEMIC_SOURCE_REQUEST:([A-Za-z0-9_=-]{1,14000})-->', turn.get('content', ''))
        if not matches:
            continue
        try:
            data = json.loads(base64.urlsafe_b64decode(matches[-1]).decode())
            phrases = data.get('retrieval_queries')
            if (data.get('scope') not in {'topic', 'course'} or not isinstance(phrases, list)
                    or len(phrases) > 4 or any(not isinstance(x, str) or len(x) > 160 for x in phrases)
                    or not isinstance(data.get('resolved_query'), str)
                    or len(data['resolved_query']) > 8000):
                return None
            return data
        except (ValueError, TypeError, AttributeError, UnicodeError):
            return None
    return None
