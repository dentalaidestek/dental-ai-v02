"""Budgeted whole-note context for small published courses, without model calls.

This supplements retrieval, not source authorization or request interpretation.
It does not read source blobs, rebuild indexes or certify model answers.
"""
from sqlalchemy import text

MAX_CONTEXT_ROWS = 128
MAX_CONTEXT_CHARS = 48000
MAX_CONTEXT_SCAN_PAGES = 4


def small_note_context(session, *, owner_user_id, course_id):
    """Return every factual row only when the complete set fits one request."""
    params = {'owner': owner_user_id, 'course': course_id}
    totals = session.exec(text('''SELECT COUNT(*),
        COALESCE(SUM(length(coalesce(c.text_content,'')) +
                     length(coalesce(c.section_title,'')) + 200),0)
        FROM studyindexchunk c JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.course_id=c.course_id AND m.active_index_version=c.index_version
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND c.content_kind <> 'QUESTION' '''), params=params).first()
    if not totals or not 0 < int(totals[0]) <= MAX_CONTEXT_ROWS or int(totals[1]) > MAX_CONTEXT_CHARS:
        return None
    # Count scans before hydrating rows. Large visual courses stay on the
    # normal query-specific retrieval path rather than paying for every image.
    scanned = session.exec(text('''SELECT DISTINCT p.material_id,p.page_number
        FROM studyindexpage p JOIN studymaterial m
          ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
         AND m.course_id=p.course_id AND m.active_index_version=p.index_version
        WHERE p.owner_user_id=:owner AND p.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND (p.extraction_method LIKE '%OCR%' OR p.extraction_method='IMAGE')
        LIMIT :scan_limit'''), params={**params, 'scan_limit': MAX_CONTEXT_SCAN_PAGES + 1}).all()
    if len(scanned) > MAX_CONTEXT_SCAN_PAGES:
        return None
    from app.academic_source_batches import load_owned_source_rows
    rows = list(load_owned_source_rows(session, **dict(owner_user_id=owner_user_id, course_id=course_id)))
    if len(rows) != int(totals[0]):
        raise ValueError('source generation changed during context planning')
    if sum(len(row[7] or '') + len(row[5] or '') + 200 for row in rows) > MAX_CONTEXT_CHARS:
        return None
    return rows
