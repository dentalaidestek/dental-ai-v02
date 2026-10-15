"""Complete native text for already-selected, owned source pages.

The persisted page checkpoint can retain a value that old search chunks lost.
This is a bounded read of the active generation, never OCR or a model call.
Question pages stay on the original-page/transcription path.
"""
import json
from sqlalchemy import text


def selected_native_pages(session, *, owner_user_id, course_id, evidence):
    bind = getattr(session, 'get_bind', lambda: None)()
    if getattr(getattr(bind, 'dialect', None), 'name', '') != 'postgresql' or not evidence:
        return {}
    selected = {(e.material_id, page) for e in evidence
                for page in range(e.page_start, e.page_end + 1)}
    rows = session.exec(text('''
        SELECT p.material_id,p.page_number,m.display_name,p.text_content
        FROM studyindexpage p JOIN studymaterial m
          ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
         AND m.course_id=p.course_id AND m.active_index_version=p.index_version
        WHERE p.owner_user_id=:owner AND p.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND p.extraction_method='PDF_TEXT' AND p.status='EXTRACTED'
          AND p.material_id=ANY(:ids) AND p.page_number=ANY(:pages)
          AND EXISTS (
            SELECT 1 FROM studyindexchunk chosen WHERE chosen.id=ANY(:chunk_ids)
              AND chosen.material_id=p.material_id AND chosen.owner_user_id=p.owner_user_id
              AND chosen.course_id=p.course_id AND chosen.index_version=p.index_version
              AND chosen.page_start<=p.page_number AND chosen.page_end>=p.page_number)
          AND NOT EXISTS (
            SELECT 1 FROM studyindexchunk q WHERE q.material_id=p.material_id
              AND q.owner_user_id=p.owner_user_id AND q.course_id=p.course_id
              AND q.index_version=p.index_version AND q.content_kind='QUESTION'
              AND q.page_start<=p.page_number AND q.page_end>=p.page_number)
        ORDER BY p.material_id,p.page_number
    '''), params={'owner':owner_user_id,'course':course_id,
                 'chunk_ids':[e.chunk_id for e in evidence],
                 'ids':sorted({m for m,_ in selected}),
                 'pages':sorted({p for _,p in selected})}).all()
    from app.study_chunking import chunk_dental_page
    result = {}
    for material, page, name, body in rows:
        key = (int(material), int(page))
        if key not in selected or not body or any(c.content_kind == 'QUESTION' for c in chunk_dental_page(body)):
            continue
        result[key] = (f'[KANIT_NATIVE material_id={key[0]} sayfa={key[1]} '
                       f'dosya={json.dumps(name, ensure_ascii=False)} tür=PDF_TEXT]\n{body}')
    return result


def apply_native_pages(result, native):
    if not native:
        return
    # Keep evidence IDs for attribution. Replace only context whose complete
    # page span is covered by the native checkpoint; preserve all scan notices.
    covered = tuple(f'[KANIT material_id={item.material_id} sayfa={item.page_start} '
        for item in result.evidence if
        {(item.material_id,p) for p in range(item.page_start,item.page_end+1)} <= native.keys())
    # Scan warnings may precede the evidence blocks; never zip this list to IDs.
    result.note_context = [context for context in result.note_context
                           if not context.startswith(covered)]
    result.note_context.extend(native.values())
