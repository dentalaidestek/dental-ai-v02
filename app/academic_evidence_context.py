"""Budgeted whole-note context for small published courses, without model calls.

This supplements retrieval, not source authorization or request interpretation.
It does not read source blobs, rebuild indexes or certify model answers.
"""
from sqlalchemy import text

MAX_CONTEXT_ROWS = 128
MAX_CONTEXT_CHARS = 48000


def small_note_context(session, *, owner_user_id, course_id):
    """Return every factual row only when the complete set fits one request."""
    params = {'owner': owner_user_id, 'course': course_id}
    # One extra row proves that a course cannot fit. Do not detoast and sum
    # every published chunk merely to reject a large course on each question.
    totals = session.exec(text('''SELECT COUNT(*),
        COALESCE(SUM(length(coalesce(candidate.text_content,'')) +
                     length(coalesce(candidate.section_title,'')) + 200),0)
        FROM (SELECT c.text_content,c.section_title
        FROM studyindexchunk c JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.course_id=c.course_id AND m.active_index_version=c.index_version
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND c.content_kind <> 'QUESTION'
        LIMIT :candidate_limit) candidate'''),
        params={**params, 'candidate_limit': MAX_CONTEXT_ROWS + 1}).first()
    if not totals or not 0 < int(totals[0]) <= MAX_CONTEXT_ROWS or int(totals[1]) > MAX_CONTEXT_CHARS:
        return None
    # This path is only used for text requests. Indexed OCR is text too;
    # scan count must not reject a complete context that fits both budgets.
    from app.academic_source_batches import load_owned_source_rows
    rows = list(load_owned_source_rows(session, **dict(owner_user_id=owner_user_id, course_id=course_id)))
    if len(rows) != int(totals[0]):
        raise ValueError('source generation changed during context planning')
    if sum(len(row[7] or '') + len(row[5] or '') + 200 for row in rows) > MAX_CONTEXT_CHARS:
        return None
    return rows
