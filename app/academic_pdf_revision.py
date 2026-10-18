"""Apply bounded changes to owned PDF text; untouched text never goes through generation."""
import json
import hashlib
import re
from sqlmodel import select


def append_saved_pdf(session, *, message_model, plan, owner_user_id, course_id, history):
    from app.academic_pdf import MAX_PDF_TEXT
    from app.study_retrieval_v2 import RetrievalResult

    def unavailable(message):
        return RetrievalResult(resolved_query=plan.resolved_query,
            retrieval_mode='pdf_append_unavailable', clarification=message)

    if message_model is None:
        return unavailable('Eklenecek içerik ve önceki PDF doğrulanamadı.')
    turns = history[-8:]
    indices = plan.pdf_addition_turns or tuple(
        i for i in range(len(turns)-1, -1, -1)
        if str(turns[i].get('role', '')).upper() == 'ASSISTANT')[:1]
    if not indices or any(i >= len(turns) for i in indices):
        return unavailable('PDF’ye eklenecek önceki cevabı belirtir misin?')
    selected = [turns[i] for i in indices]
    if any(str(t.get('role', '')).upper() != 'ASSISTANT'
           or str(t.get('mode', '')).endswith('_PDF')
           or type(t.get('id')) is not int for t in selected):
        return unavailable('PDF’ye eklenecek mevcut tablo veya cevabı belirtir misin?')
    # Re-read every chosen row with ownership/course fences. Model output only
    # chooses bounded dialogue positions, never arbitrary database identifiers.
    ids = [t['id'] for t in selected]
    rows = list(session.exec(select(message_model).where(
        message_model.owner_user_id == owner_user_id,
        message_model.course_id == course_id,
        message_model.role == 'ASSISTANT', message_model.id.in_(ids),
    ).order_by(message_model.id)).all())
    if (len(rows) != len(ids) or any(not row.content.strip()
            or row.mode.endswith('_PDF') for row in rows)):
        return unavailable('Eklenecek cevap artık bulunamadı; PDF oluşturulmadı.')
    base = session.exec(select(message_model).where(
        message_model.owner_user_id == owner_user_id,
        message_model.course_id == course_id,
        message_model.role == 'ASSISTANT',
        message_model.mode.endswith('_PDF', autoescape=True),
        message_model.id < rows[0].id,
    ).order_by(message_model.id.desc()).limit(1)).first()
    if base is None or not base.content.strip():
        return unavailable('Bu sohbette eklenecek içeriğin öncesinde oluşturulmuş PDF bulunamadı. Hangi PDF’ye ekleyelim?')
    parts = [base.content]
    for row in rows:
        if row.content not in parts:
            parts.append(row.content)
    total = sum(map(len, parts)) + 2 * (len(parts)-1)
    if total > MAX_PDF_TEXT:
        return unavailable('Birleştirilmiş içerik PDF uzunluk sınırını aşıyor; mevcut PDF korunuyor.')
    return RetrievalResult(resolved_query=plan.resolved_query,
        retrieval_mode='appended_answer_pdf', evidence_sufficient=True,
        prepared_answer='\n\n'.join(parts), study_task={'pdf_revision_applied': True})


EDIT_ACTIONS = {'append', 'prepend', 'insert_before', 'insert_after', 'replace', 'delete'}
EDIT_FIELDS = {'action', 'target', 'extent', 'source', 'content', 'turns'}


def validate_edit_contract(data):
    edits, base = data['pdf_edits'], data['pdf_base_turn']
    if base is not None and (type(base) is not int or not 0 <= base < 8):
        raise ValueError('invalid PDF version')
    if not isinstance(edits, list) or len(edits) > 8:
        raise ValueError('invalid edit count')
    if not edits:
        if base is not None:
            raise ValueError('unused PDF version')
        return
    if (data['operation'] != 'answer' or data['output_format'] != 'pdf'
            or data['append_previous_pdf'] or data['export_previous_answer'] or data['grade_previous_set']):
        raise ValueError('incompatible PDF edit')
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != EDIT_FIELDS:
            raise ValueError('invalid edit fields')
        action, source = edit['action'], edit['source']
        if action not in EDIT_ACTIONS or edit['extent'] not in {'match', 'section'}:
            raise ValueError('invalid edit action')
        if source not in {'chat', 'literal', 'generate', 'none'}:
            raise ValueError('invalid edit source')
        if any(not isinstance(edit[k], str) or len(edit[k]) > 20000 or '\x00' in edit[k]
               for k in ('target', 'content')):
            raise ValueError('invalid edit text')
        turns = edit['turns']
        if (not isinstance(turns, list) or len(turns) > 8 or len({str(i) for i in turns}) != len(turns)
                or any(type(i) is not int or not 0 <= i < 8 for i in turns)):
            raise ValueError('invalid edit turns')
        if action in {'append', 'prepend'}:
            if edit['target'] or edit['extent'] != 'match':
                raise ValueError('unused edit target')
        elif not edit['target'].strip():
            raise ValueError('missing edit target')
        if action == 'delete':
            if source != 'none' or edit['content'] or turns:
                raise ValueError('invalid deletion')
        elif source == 'none' or (source == 'literal' and not edit['content'].strip()):
            raise ValueError('missing replacement')
        if (source != 'literal' and edit['content']) or (source != 'chat' and turns):
            raise ValueError('unused edit content')


def latest_owned_pdf(session, message_model, owner_user_id, course_id):
    return session.exec(select(message_model).where(
        message_model.owner_user_id == owner_user_id, message_model.course_id == course_id,
        message_model.role == 'ASSISTANT', message_model.mode.endswith('_PDF', autoescape=True),
    ).order_by(message_model.id.desc()).limit(1)).first()


def planner_pdf_outline(session, message_model, owner_user_id, course_id, outline):
    result = dict(outline) if isinstance(outline, dict) else {}
    base = latest_owned_pdf(session, message_model, owner_user_id, course_id)
    if base is not None:
        result['editable_pdf'] = {'content': base.content,
            'revision': hashlib.sha256(base.content.encode('utf-8')).hexdigest()}
    return result


def target_span(body, edit):
    action, target = edit['action'], edit['target']
    if action == 'append':
        return len(body), len(body)
    if action == 'prepend':
        return 0, 0
    start = body.find(target)
    if start < 0 or body.find(target, start+1) >= 0:
        raise ValueError('Hedef metin PDF’de bulunamadı veya birden fazla yerde var. Başlığı ya da cümleyi açıkça belirtir misin?')
    end = start + len(target)
    if edit['extent'] == 'section':
        line_start = body.rfind('\n', 0, start)+1
        line_end = body.find('\n', end)
        line_end = len(body) if line_end < 0 else line_end
        line = body[line_start:line_end]
        heading = re.fullmatch(r' {0,3}(#{1,6})\s+.+', line)
        if not heading or line.strip() != target.strip():
            raise ValueError('Değiştirilecek bölümün tam başlığını belirtir misin?')
        following = re.search(r'^ {0,3}#{1,'+str(len(heading[1]))+r'}\s+', body[line_end:], re.MULTILINE)
        start = line_start
        end = line_end+following.start() if following else len(body)
    if action == 'insert_before':
        return start, start
    if action == 'insert_after':
        return end, end
    return start, end


def apply_pdf_edits(state, generated=None):
    from app.academic_pdf import MAX_PDF_TEXT
    generated = generated or {}
    body = state['body']
    for edit in sorted(state['edits'], key=lambda e: (e['start'], e['end']), reverse=True):
        content = generated.get(edit['id']) if edit['source'] == 'generate' else edit['content']
        if not isinstance(content, str) or (edit['action'] != 'delete' and not content.strip()):
            raise ValueError('İstenen PDF değişikliği tamamlanamadı; önceki PDF korunuyor.')
        if edit['action'] in {'append', 'prepend', 'insert_before', 'insert_after'}:
            content = ('\n\n' if edit['start'] else '') + content + ('\n\n' if edit['end'] < len(state['body']) else '')
        body = body[:edit['start']] + content + body[edit['end']:]
        if len(body) > MAX_PDF_TEXT:
            raise ValueError('Düzenlenmiş içerik PDF uzunluk sınırını aşıyor; önceki PDF korunuyor.')
    if not body.strip():
        raise ValueError('Bu değişiklik PDF’nin bütün içeriğini siliyor; önceki PDF korunuyor.')
    return body


def prepare_pdf_revision(session, *, message_model, plan, owner_user_id, course_id, history, query, snapshot=None):
    from app.study_retrieval_v2 import RetrievalResult
    def unavailable(message):
        return RetrievalResult(resolved_query=plan.resolved_query,
            retrieval_mode='pdf_edit_unavailable', clarification=message)
    if message_model is None:
        return unavailable('Düzenlenecek PDF doğrulanamadı.')
    turns = history[-8:]
    if plan.pdf_base_turn is None:
        base = latest_owned_pdf(session, message_model, owner_user_id, course_id)
    else:
        index = plan.pdf_base_turn
        candidate = turns[index] if index < len(turns) else {}
        base = session.exec(select(message_model).where(
            message_model.id == candidate.get('id'), message_model.owner_user_id == owner_user_id,
            message_model.course_id == course_id, message_model.role == 'ASSISTANT',
            message_model.mode.endswith('_PDF', autoescape=True),
        )).first() if candidate.get('is_pdf') or str(candidate.get('mode', '')).endswith('_PDF') else None
    if base is None or not base.content.strip():
        return unavailable('Düzenlenecek önceki PDF bulunamadı. Hangi PDF’yi düzenleyelim?')
    if (plan.pdf_base_turn is None and snapshot
            and hashlib.sha256(base.content.encode('utf-8')).hexdigest() != snapshot):
        return unavailable('PDF bu sırada güncellenmiş. Son sürüm üzerinde isteğini yeniden gönderir misin?')
    if plan.pdf_base_turn is not None and candidate.get('content') is not None and candidate['content'] != base.content:
        return unavailable('Seçilen PDF sürümü değişmiş; lütfen yeniden gönder.')
    edits = []
    try:
        for number, edit in enumerate(plan.pdf_edits):
            start, end = target_span(base.content, edit)
            content = edit['content']
            if edit['source'] == 'literal' and content not in query:
                raise ValueError('Yeni metni mesajında aynen belirtir misin?')
            if edit['source'] == 'chat':
                indices = edit['turns'] or [i for i in range(len(turns)-1, -1, -1)
                    if str(turns[i].get('role', '')).upper() == 'ASSISTANT'
                    and not str(turns[i].get('mode', '')).endswith('_PDF')][:1]
                if not indices or any(i >= len(turns) for i in indices):
                    raise ValueError('Eklenecek mevcut tablo veya cevabı belirtir misin?')
                ids = [turns[i].get('id') for i in indices]
                if any(type(id) is not int for id in ids) or len(set(ids)) != len(ids):
                    raise ValueError('Eklenecek cevap doğrulanamadı.')
                rows = list(session.exec(select(message_model).where(
                    message_model.id.in_(ids), message_model.owner_user_id == owner_user_id,
                    message_model.course_id == course_id, message_model.role == 'ASSISTANT',
                ).order_by(message_model.id)).all())
                if len(rows) != len(ids) or any(not row.content.strip() or row.mode.endswith('_PDF') for row in rows):
                    raise ValueError('Eklenecek cevap artık bulunamadı.')
                content = '\n\n'.join(row.content for row in rows)
            edits.append({**edit, 'id': number, 'start': start, 'end': end,
                          'content': content, 'original': base.content[start:end]})
        for i, first in enumerate(edits):
            for second in edits[i+1:]:
                if (max(first['start'], second['start']) < min(first['end'], second['end'])
                        or first['start'] == second['start']
                        or first['start'] < second['start'] < first['end']
                        or second['start'] < first['start'] < second['end']):
                    raise ValueError('Değiştirilecek bölümler çakışıyor. Ayrı hedefleri belirtir misin?')
        state = {'body': base.content, 'edits': edits}
        if any(e['source'] == 'generate' for e in edits):
            return RetrievalResult(resolved_query=plan.resolved_query,
                retrieval_mode='pdf_edit_generation', pdf_revision=state)
        answer = apply_pdf_edits(state)
        return RetrievalResult(resolved_query=plan.resolved_query,
            retrieval_mode='edited_answer_pdf', prepared_answer=answer, evidence_sufficient=True,
            study_task={'pdf_revision_applied': True})
    except ValueError as exc:
        return unavailable(str(exc))


PATCH_SCHEMA = {'type': 'object', 'properties': {'patches': {'type': 'array', 'maxItems': 8,
    'items': {'type': 'object', 'properties': {'id': {'type': 'integer'},
        'content': {'type': 'string'}, 'supported': {'type': 'boolean'}},
        'required': ['id', 'content', 'supported'], 'additionalProperties': False}}},
    'required': ['patches'], 'additionalProperties': False}


def generated_patch_content(raw, state):
    data = json.loads(raw)
    expected = {edit['id'] for edit in state['edits'] if edit['source'] == 'generate'}
    if not isinstance(data, dict) or set(data) != {'patches'} or not isinstance(data['patches'], list):
        raise ValueError('invalid PDF patches')
    result = {}
    for patch in data['patches']:
        if (not isinstance(patch, dict) or set(patch) != {'id', 'content', 'supported'}
                or type(patch['id']) is not int or patch['id'] not in expected or patch['id'] in result
                or patch['supported'] is not True or not isinstance(patch['content'], str)
                or not patch['content'].strip()):
            raise ValueError('incomplete or unsupported PDF changes')
        result[patch['id']] = patch['content']
    if set(result) != expected:
        raise ValueError('missing PDF change')
    return result
